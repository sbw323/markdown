# WWDR Pipeline: Wastewater Data Research Processing System

## Project Overview

The WWDR (WasteWater Data Research) Pipeline is a Python-based toolkit for processing and analyzing simulation outputs from ASM3 (Activated Sludge Model No. 3), a mathematical model used to simulate biological wastewater treatment processes. The project consolidates what was originally 10+ separate Python scripts into a unified, maintainable system that transforms raw simulation data into analyzable datasets and visualizations.

## The Problem Being Solved

Wastewater treatment simulations generate large volumes of time-series data across multiple reactor units and experimental conditions. Researchers need to:

- **Stack** iteration outputs from hundreds of simulation runs into coherent datasets
- **Normalize** experimental results against baseline conditions to identify deviations
- **Extract** specific time windows (e.g., the first 3 days of operation)
- **Aggregate** results by experiment parameters (duration, operating conditions)
- **Visualize** trends in key metrics like ammonia (S_NH4) and chemical oxygen demand (COD)

The original workflow involved running separate scripts sequentially, manually managing file paths, and dealing with inconsistent naming conventions—a process prone to errors and difficult to reproduce.

## Technical Challenges

### 1. **Data Alignment Complexity**
Simulation outputs arrive as separate CSV files for each reactor unit (R1-R5) and settler (S) across multiple iterations. These must be:
- Aligned on quarter-hour timestamp boundaries
- Stacked vertically while preserving source tracking
- Merged with influent (incoming wastewater) characteristics
- Normalized against nominal baseline conditions

### 2. **Naming Convention Standardization**
Different simulation outputs use inconsistent naming:
- Settler variables need an 'e' suffix (CODe, SNH4e for effluent measurements)
- Reactor variables need 'r#' suffixes (CODr1, CODr2 for reactor stages)
- Automatic header detection required for CSV files lacking column names

### 3. **Configuration vs. Flexibility Trade-off**
The pipeline must support:
- **Quick iteration** during development (running individual stages with custom parameters)
- **Reproducible batch processing** for production (configuration-driven full pipeline execution)
- **Hybrid workflows** where researchers override config defaults for specific experiments

### 4. **Code Duplication and Maintenance**
The original scripts contained:
- Redundant CSV loading and timestamp handling code
- Duplicate normalization calculations (removed obsolete EQI calculations, retained COD metrics)
- Inconsistent error handling and logging patterns
- Hard-coded file paths scattered across multiple files

## Current Solution Architecture

The consolidated WWDR-Pipeline implements a **six-stage modular architecture**:

1. **Stack** (`stacker.py`): Concatenates iteration outputs, generates synthetic timestamps
2. **Join Influent** (`influent.py`): Merges influent data using ticker-based alignment
3. **Normalize** (`normalizer.py`): Computes normalized difference metrics against baselines
4. **Extract** (`extractor.py`): Isolates specific time windows for analysis
5. **Aggregate** (`aggregator.py`): Groups datasets by experiment length or conditions
6. **Plot** (`plots.py`): Generates publication-ready visualizations

### Key Implementation Features

- **Hybrid CLI**: Uses Click for both individual subcommands (`wwdr stack`, `wwdr normalize`) and configuration-driven execution (`wwdr run --config pipeline.yaml`)
- **Configuration Management**: Pydantic models validate YAML configs, preventing runtime errors
- **Automatic Fallbacks**: Header detection for CSV files, directory path resolution, missing data handling
- **Comprehensive Logging**: Structured logging with configurable verbosity levels
- **Type Safety**: Python 3.11+ type hints throughout for improved maintainability

## Recent Milestones

Successfully consolidated 10+ scripts into cohesive package structure  
Resolved CSV header detection issues in influent data  
Fixed nominal baseline directory path configuration  
Implemented unified normalization for both S_NH4 and COD metrics  
Created reproducible configuration system with YAML validation  

## Use Cases

**Development Workflow**: Researcher testing a new normalization algorithm runs `wwdr normalize --input-dir ./test_data --baseline-dir ./baseline` to quickly iterate on a single stage.

**Production Workflow**: Batch processing 50 experimental datasets runs `wwdr run --config longterm_pipeline.yaml` to execute all six stages consistently across experiments.

**Hybrid Workflow**: Re-running just the plotting stage with different parameters: `wwdr plot --config pipeline.yaml --day day2 --metric COD_inf_norm`

## Success Metrics

The project's success is measured by:
- **Code reduction**: 10 separate scripts → 1 unified package
- **Reproducibility**: Configuration files in version control guarantee identical results
- **Flexibility**: Individual commands available for development iteration
- **Maintainability**: Shared utilities eliminate duplication, type hints catch errors early
- **User experience**: Clear CLI with helpful error messages, automatic path resolution

This consolidation transforms a collection of brittle scripts into a robust research tool that scales from quick exploratory analysis to reproducible publication-quality data processing.