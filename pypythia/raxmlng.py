import pathlib
import subprocess
from tempfile import TemporaryDirectory
from typing import Optional

from pypythia.config import DEFAULT_RAXMLNG_EXE
from pypythia.custom_errors import RAxMLNGError


def run_raxmlng_command(cmd: list[str]) -> None:
    """Helper method to run a RAxML-NG command.

    Args:
        cmd (list): List of strings representing the RAxML-NG command to run.

    Raises:
        RAxMLNGError: If the RAxML-NG command fails with a CalledProcessError.
        RuntimeError: If the RAxML-NG command fails with any other error.
    """
    try:
        subprocess.check_output(cmd, encoding="utf-8")
    except subprocess.CalledProcessError as e:
        raise RAxMLNGError(subprocess_exception=e)
    except Exception as e:
        raise RuntimeError("Running RAxML-NG command failed.") from e


def _get_value_from_line(line: str, search_string: str) -> float:
    line = line.strip()
    if search_string in line:
        _, value = line.rsplit(" ", 1)
        return float(value)

    raise ValueError(
        f"The given line '{line}' does not contain the search string '{search_string}'."
    )


def _get_raxmlng_rfdist_results(log_file: pathlib.Path) -> tuple[float, float, float]:
    abs_rfdist = None
    rel_rfdist = None
    num_topos = None

    for line in log_file.open().readlines():
        line = line.strip()

        if "Average absolute RF distance in this tree set:" in line:
            abs_rfdist = _get_value_from_line(
                line, "Average absolute RF distance in this tree set:"
            )
        elif "Average relative RF distance in this tree set:" in line:
            rel_rfdist = _get_value_from_line(
                line, "Average relative RF distance in this tree set:"
            )
        elif "Number of unique topologies in this tree set:" in line:
            num_topos = _get_value_from_line(
                line, "Number of unique topologies in this tree set:"
            )

    if abs_rfdist is None or rel_rfdist is None or num_topos is None:
        raise ValueError("Error parsing raxml-ng log.")

    return num_topos, rel_rfdist, abs_rfdist


class RAxMLNG:
    """Class to interact with the RAxML-NG binary.

    Args:
        exe_path (pathlib.Path, optional): Path to the RAxML-NG executable. Defaults to the binary found in the PATH environment variable.

    Attributes:
        exe_path (pathlib.Path): Path to the RAxML-NG executable.
    """

    def __init__(self, exe_path: Optional[pathlib.Path] = DEFAULT_RAXMLNG_EXE):
        self.exe_path = exe_path

    def _base_cmd(
        self, msa_file: pathlib.Path, model: str, prefix: pathlib.Path, **kwargs
    ) -> list[str]:
        additional_settings = []
        for key, value in kwargs.items():
            if value is None:
                additional_settings += [f"--{key}"]
            else:
                additional_settings += [f"--{key}", str(value)]

        return [
            str(self.exe_path.absolute()),
            "--msa",
            str(msa_file.absolute()),
            "--model",
            model,
            "--prefix",
            str(prefix.absolute()),
            *additional_settings,
        ]

    def _run_alignment_parse(
        self, msa_file: pathlib.Path, model: str, prefix: pathlib.Path, **kwargs
    ) -> None:
        cmd = self._base_cmd(msa_file, model, prefix, parse=None, **kwargs)
        run_raxmlng_command(cmd)

    def _run_rfdist(
        self, trees_file: pathlib.Path, prefix: pathlib.Path, **kwargs
    ) -> None:
        additional_settings = []
        for key, value in kwargs.items():
            if value is None:
                additional_settings += [f"--{key}"]
            else:
                additional_settings += [f"--{key}", str(value)]
        cmd = [
            str(self.exe_path.absolute()),
            "--rfdist",
            str(trees_file.absolute()),
            "--prefix",
            str(prefix.absolute()),
            *additional_settings,
        ]
        run_raxmlng_command(cmd)

    def infer_parsimony_trees(
        self,
        msa_file: pathlib.Path,
        model: str,
        prefix: pathlib.Path,
        n_trees: int = 24,
        **kwargs,
    ) -> pathlib.Path:
        """Method that infers n_trees using the RAxML-NG implementation of maximum parsimony.

        Args:
            msa_file (pathlib.Path): Filepath pointing to the MSA file.
            model (str): String representation of the substitution model to use. Needs to be a valid RAxML-NG model.
                For example "GTR+G" for DNA data or "LG+G" for protein data.
            prefix (pathlib.Path): Prefix to use when running RAxML-NG.
            n_trees (int): Number of trees to infer. Defaults to 24.
            **kwargs: Additional arguments to pass to the RAxML-NG command.
                The name of the kwarg needs to be a valid RAxML-NG flag.
                For flags with a value pass it like this: "flag=value", for flags without a value pass it like this: "flag=None".
                See https://github.com/amkozlov/raxml-ng for all options.

        Returns:
            Filepath pointing to the inferred maximum parsimony trees.
        """
        cmd = self._base_cmd(
            msa_file, model, prefix, start=None, tree=f"pars{{{n_trees}}}", **kwargs
        )
        run_raxmlng_command(cmd)
        return pathlib.Path(f"{prefix}.raxml.startTree")

    def get_rfdistance_results(
        self, trees_file: pathlib.Path, prefix: pathlib.Path = None, **kwargs
    ) -> tuple[float, float, float]:
        """Method that computes the number of unique topologies, relative RF-Distance, and absolute RF-Distance for the given set of trees.

        Args:
            trees_file (pathlib.Path): Filepath pointing to the file containing the trees.
            prefix (pathlib.Path, optional): Prefix to use when running RAxML-NG. Defaults to None. If None, a temporary directory is used.
            **kwargs: Additional arguments to pass to the RAxML-NG command.
                The name of the kwarg needs to be a valid RAxML-NG flag.
                For flags with a value pass it like this: "flag=value", for flags without a value pass it like this: "flag=None".
                See

        Returns:
            num_topos (float): Number of unique topologies of the given set of trees.
            rel_rfdist (float): Relative RF-Distance of the given set of trees. Computed as average over all pairwise RF-Distances. Value between 0.0 and 1.0.
            abs_rfdist (float): Absolute RF-Distance of the given set of trees.
        """
        with TemporaryDirectory() as tmpdir:
            tmpdir = pathlib.Path(tmpdir)
            if not prefix:
                prefix = tmpdir / "rfdist"
            self._run_rfdist(trees_file, prefix, **kwargs)
            log_file = pathlib.Path(f"{prefix}.raxml.log")
            return _get_raxmlng_rfdist_results(log_file)
