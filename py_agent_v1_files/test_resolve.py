# tests/test_resolve.py
import pytest

# Import after deployment — adjust path as needed
from orchestrator import _resolve


@pytest.fixture
def project_root(tmp_path):
    """Create a fake project root with known structure."""
    (tmp_path / "leyp_config.py").write_text("# config")
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "checkpoint.py").write_text("# ckpt")
    return tmp_path


class TestResolveSandbox:
    """Verify _resolve blocks all escape vectors."""

    def test_relative_path_within_root(self, project_root):
        result = _resolve("leyp_config.py", project_root)
        assert result == project_root / "leyp_config.py"

    def test_nested_relative_path(self, project_root):
        result = _resolve("config/checkpoint.py", project_root)
        assert result == project_root / "config" / "checkpoint.py"

    def test_absolute_path_within_root(self, project_root):
        abs_path = str(project_root / "leyp_config.py")
        result = _resolve(abs_path, project_root)
        assert result == project_root / "leyp_config.py"

    def test_absolute_path_outside_root_blocked(self, project_root):
        with pytest.raises(ValueError, match="escapes project root"):
            _resolve("/etc/passwd", project_root)

    def test_absolute_path_to_tmp_blocked(self, project_root):
        with pytest.raises(ValueError, match="escapes project root"):
            _resolve("/tmp/evil.py", project_root)

    def test_relative_traversal_blocked(self, project_root):
        with pytest.raises(ValueError, match="escapes project root"):
            _resolve("../../etc/passwd", project_root)

    def test_prefix_collision_blocked(self, project_root):
        """Sibling directory with matching prefix must be rejected."""
        sibling = project_root.parent / (project_root.name + "_evil")
        sibling.mkdir(exist_ok=True)
        (sibling / "steal.py").write_text("# evil")
        evil_relative = f"../{project_root.name}_evil/steal.py"
        with pytest.raises(ValueError, match="escapes project root"):
            _resolve(evil_relative, project_root)

    def test_root_itself_allowed(self, project_root):
        """Resolving '.' should return the root (for dir listing)."""
        result = _resolve(".", project_root)
        assert result == project_root

    def test_dot_dot_at_root_level_blocked(self, project_root):
        with pytest.raises(ValueError, match="escapes project root"):
            _resolve("..", project_root)
