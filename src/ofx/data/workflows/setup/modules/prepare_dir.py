"""Create a temporary directory to hold the lab compose files."""
import pathlib
import tempfile


def run(ctx):
    lab_dir = pathlib.Path(tempfile.mkdtemp(prefix="ofx_lab_"))
    lab_dir.chmod(0o755)
    ctx.add_outputs(lab_dir=str(lab_dir))
    print(f"Lab directory: {lab_dir}")
