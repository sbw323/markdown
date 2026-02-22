import os
import re
import json
import subprocess
from pydantic import BaseModel
from google import genai
from google.genai import types

# =====================================================================
# 1. STRUCTURED OUTPUT SCHEMA
# =====================================================================
class QAEvaluation(BaseModel):
    is_approved: bool
    feedback_for_developer: str

# =====================================================================
# 2. SYSTEM PROMPTS (From Experiment Plan)
# =====================================================================
DEV_SYSTEM_PROMPT = """You are the Lead Developer Agent, an expert in Python orchestration and MATLAB/Simulink integration. Your objective is to implement the "Dynamic Step-Response Simulation" framework exactly as specified in the provided Experiment Plan document.

You are operating in a VM environment where you can write, execute, and debug both Python and MATLAB code. You are paired with an adversarial QA Agent who will ruthlessly audit your code and test it in the VM.

Your Workflow (The Loop):

Read the Plan: Reference the attached Experiment Plan for all architectural boundaries, formulas, and constraints.
Work in Tranches: You will develop the system in four sequential tranches (defined below).
Execute & Submit: For each tranche, write the code, perform basic execution checks in the VM, and then write a file named TRANCHE_READY.md detailing what is ready for review.
Wait: Pause execution and wait for the QA Agent.
Review Feedback: The QA Agent will output a QA_STATUS.md file containing either PASS or FAIL, along with a QA_FEEDBACK.md artifact.
If FAIL: Read the feedback, fix the code, verify in the VM, and resubmit.
If PASS: Proceed immediately to the next tranche.
Completion: You may only stop when Tranche 4 is completed and receives a PASS.
Development Tranches:

Tranche 1 (Data & Config): config.yaml, influent_generator.py, profile_generator.py. (Ref: Sections 3, 4, 5.2-5.4).
Tranche 2 (MATLAB Engine): ssASM3_DR_datagen.m and ssData_writer_reliability.m. Critical: You must perfectly implement the 3-step protocol, state inheritance, and ensure benchmarkinit is ONLY called in Step A. (Ref: Sections 2, 5.6-5.7).
Tranche 3 (Orchestration & Metrics): metrics.py and orchestrator.py. Critical: Respect the Python/MATLAB boundary. Python does NO physics/biology. (Ref: Sections 1.3, 5.2, 5.5).
Tranche 4 (Integration): End-to-end execution of the 165-simulation matrix and generation of the README.md.
Strict Constraints:

Never calculate sCOD, energy, or biological kinetics in Python.
Preserve the clear all + reload workspace survival pattern in MATLAB.
Do not hardcode paths; use the YAML config and sim_config.mat.
Begin by reading the plan and starting Tranche 1.
"""

QA_SYSTEM_PROMPT = ""You are the Adversarial QA Agent, a ruthless automation engineer and code auditor. Your objective is to ensure the Developer Agent's code strictly adheres to the provided Experiment Plan, particularly the architectural boundaries and MATLAB state-machine logic.

You operate in the same VM environment as the Developer. You can execute Python (pytest) and MATLAB scripts.

Your Workflow (The Loop):

Wait for Submission: Monitor the workspace for TRANCHE_READY.md from the Developer.
Audit & Test: When a tranche is ready, you must:
Write the corresponding test scripts defined in Section 6 of the Experiment Plan (e.g., test_influent_generator.py, validate_matlab_logic.m).
Execute the tests in the VM. Static analysis is not enough; you must run the code.
Audit the code against the strict constraints (e.g., check Python files for banned biological calculations; check MATLAB files to ensure benchmarkinit is gated to Step 1).
Generate Feedback:
Create a QA_FEEDBACK.md artifact detailing every bug, boundary violation, or failed test.
Create a QA_STATUS.md file containing exactly one word: PASS or FAIL.
Enforce the Standard: Do not issue a PASS until the tranche executes flawlessly in the VM and perfectly aligns with the Experiment Plan.
Completion: Stop only when Tranche 4 receives a PASS and the final dataset is successfully generated.
Critical Audit Targets by Tranche:

Tranche 1: Verify 5 percentiles and 11 profiles are generated correctly. Ensure .mat files load properly in MATLAB. (Ref: Sections 6.2, 6.3).
Tranche 2: This is the highest risk area. You must verify the MATLAB script uses the clear all + reload pattern, correctly inherits workspace_baseline.mat and workspace_curtailment.mat, and NEVER calls benchmarkinit in Steps 2 or 3. (Ref: Sections 6.7).
Tranche 3: Verify Python orchestrator correctly writes sim_config.mat and handles the loop. Ensure metrics.py only does basic arithmetic. (Ref: Sections 6.4, 6.5).
Tranche 4: Verify the final CSV/Parquet database has exactly 165 rows (55 cycles * 3 steps) and no missing data. (Ref: Section 6.6).
Wait for the Developer to output TRANCHE_READY.md to begin your first audit.
"""

# =====================================================================
# 3. TRANCHE DEFINITIONS
# =====================================================================
TRANCHES = [
    {
        "name": "Tranche 1 (Data & Config)",
        "prompt": "Begin Tranche 1. Generate `config.yaml`, `influent_generator.py`, and `profile_generator.py`. Ensure influent percentiles and aeration reduction grids are correctly calculated. Output the files in markdown blocks."
    },
    {
        "name": "Tranche 2 (MATLAB Engine)",
        "prompt": "Begin Tranche 2. Generate `ssASM3_DR_datagen.m` and `ssData_writer_reliability.m`. CRITICAL: You must perfectly implement the 3-step protocol, state inheritance, and ensure `benchmarkinit` is ONLY called in Step A. Output the files in markdown blocks."
    },
    {
        "name": "Tranche 3 (Orchestration & Metrics)",
        "prompt": "Begin Tranche 3. Generate `metrics.py` and `orchestrator.py`. Respect the Python/MATLAB boundary. Python does NO physics/biology. Output the files in markdown blocks."
    },
    {
        "name": "Tranche 4 (Integration)",
        "prompt": "Begin Tranche 4. Generate a final `run_experiment.py` script that ties everything together to execute the 165-simulation matrix end-to-end. Output the file in a markdown block."
    }
]

# =====================================================================
# 4. HELPER FUNCTIONS
# =====================================================================
def extract_files(text):
    """Parses the LLM output to extract code blocks and assign filenames."""
    blocks = re.finditer(r'```(python|matlab|yaml|markdown|sh)\n(.*?)\n```', text, re.DOTALL | re.IGNORECASE)
    files = {}
    
    for match in blocks:
        lang = match.group(1).lower()
        code = match.group(2)
        
        # Look for filename in the very first line of the code block as a comment
        first_line = code.lstrip().split('\n')[0]
        fname_match = re.search(r'[#%]\s*([a-zA-Z0-9_-]+\.(?:py|m|yaml|md))', first_line)
        
        if fname_match:
            filename = fname_match.group(1)
        else:
            ext = {'python': 'py', 'matlab': 'm', 'yaml': 'yaml', 'markdown': 'md'}.get(lang, 'txt')
            filename = f"generated_file_{len(files)}.{ext}"
            
        files[filename] = code
            
    return files

def save_files(files_dict):
    """Saves extracted files to the local disk, creating directories if needed."""
    for filepath, content in files_dict.items():
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  [+] Saved: {filepath}")

# =====================================================================
# 5. MAIN ORCHESTRATOR LOOP
# =====================================================================
def main():
    print(" Starting Execution-Driven Adversarial Workflow...")
    
    # Initialize the client (automatically picks up GEMINI_API_KEY from environment)
    client = genai.Client()
    MODEL_ID = 'gemini-2.5-pro' 

    # Create stateful Chat Sessions
    dev_chat = client.chats.create(
        model=MODEL_ID,
        config=types.GenerateContentConfig(system_instruction=DEV_SYSTEM_PROMPT, temperature=0.1)
    )
    qa_chat = client.chats.create(
        model=MODEL_ID,
        config=types.GenerateContentConfig(system_instruction=QA_SYSTEM_PROMPT, temperature=0.1)
    )
    
    max_iterations_per_tranche = 5

    for tranche_idx, tranche in enumerate(TRANCHES):
        print(f"\n{'='*60}\n STARTING {tranche['name'].upper()}\n{'='*60}")
        current_dev_prompt = tranche['prompt']
        
        for attempt in range(1, max_iterations_per_tranche + 1):
            print(f"\n--- {tranche['name']} | Attempt {attempt}/{max_iterations_per_tranche} ---")
            
            # ---------------------------------------------------------
            # STEP A: DEVELOPER WRITES CODE
            # ---------------------------------------------------------
            print(" Developer Agent is writing code...")
            dev_response = dev_chat.send_message(current_dev_prompt)
            dev_files = extract_files(dev_response.text)
            
            if not dev_files:
                current_dev_prompt = "System Error: Failed to extract code. Please ensure you use ```python, ```matlab, or ```yaml blocks and include the filename in the first comment."
                continue
                
            save_files(dev_files)
            
            # ---------------------------------------------------------
            # STEP B: QA AGENT WRITES TEST SCRIPT
            # ---------------------------------------------------------
            print(" QA Agent is writing validation tests...")
            qa_test_prompt = f"The Developer has submitted files for {tranche['name']}. Please write a Python test script named `qa_test_tranche_{tranche_idx+1}.py` to validate this code in the VM. Output the code in a ```python block."
            qa_test_response = qa_chat.send_message(qa_test_prompt)
            qa_files = extract_files(qa_test_response.text)
            
            test_script_name = None
            for fname in qa_files.keys():
                if fname.endswith('.py') and 'test' in fname.lower():
                    test_script_name = fname
                    break
            
            if not test_script_name:
                print(" QA Agent failed to generate a test script. Forcing retry...")
                continue
                
            save_files(qa_files)
            
            # ---------------------------------------------------------
            # STEP C: ORCHESTRATOR EXECUTES TESTS (Ground Truth)
            # ---------------------------------------------------------
            print(f" Executing {test_script_name} in local VM...")
            try:
                # 10-minute timeout for heavy MATLAB/Simulink operations
                result = subprocess.run(["python", test_script_name], capture_output=True, text=True, timeout=600)
                stdout, stderr, rcode = result.stdout, result.stderr, result.returncode
            except subprocess.TimeoutExpired:
                stdout, stderr, rcode = "", "Execution timed out after 10 minutes.", 1
                
            print(f"Execution finished with Return Code: {rcode}")
            
            # ---------------------------------------------------------
            # STEP D: QA AGENT EVALUATES LOGS (Structured Output)
            # ---------------------------------------------------------
            print(" QA Agent is evaluating execution logs...")
            qa_eval_prompt = f"""EXECUTION RESULTS FOR {test_script_name}:
            Return Code: {rcode}
            STDOUT: {stdout[-2000:]}
            STDERR: {stderr[-2000:]}

            Review these logs based on your system instructions. Did the execution perfectly succeed and meet all Tranche requirements?"""
            
            qa_res = client.models.generate_content(
                model=MODEL_ID,
                contents=[QA_SYSTEM_PROMPT, qa_eval_prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=QAEvaluation,
                    temperature=0.0
                )
            )
            
            qa_data = json.loads(qa_res.text)
            
            if qa_data['is_approved'] and rcode == 0:
                print(f"\n QA APPROVED {tranche['name']}! Moving to next tranche.")
                break # Break out of the attempt loop, move to next tranche
            else:
                print(f"\n QA REJECTED {tranche['name']}.")
                print(f"Feedback: {qa_data['feedback_for_developer']}")
                
                # Feed the exact traceback and QA critique back to the Developer Chat
                current_dev_prompt = f"QA rejected your code. Feedback: {qa_data['feedback_for_developer']}\n\nTest STDERR:\n{stderr}\n\nPlease fix the errors and rewrite the affected files."

        else:
            print(f"\n Max iterations reached for {tranche['name']}. Halting workflow.")
            return # Stop the entire script if a tranche cannot be completed

    print("\n All Tranches Completed Successfully! The Experiment Framework is ready.")

if __name__ == "__main__":
    main()