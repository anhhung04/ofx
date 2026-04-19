"""searchsploit — command-line interface for Exploit-DB."""

from __future__ import annotations

from pathlib import Path

from ofx.tasks.base import OptDef, Task
from ofx.tasks.output_types import Exploit
from ofx.tasks.registry import TaskRegistry


@TaskRegistry.register("searchsploit")
class SearchsploitTask(Task):
    name = "searchsploit"
    cmd = "searchsploit"
    description = "Search Exploit-DB from the command line"
    category = "exploit/recon"
    install_cmd = "apt install -y exploitdb"
    output_types = [Exploit]

    opts = {
        "exact": OptDef(flag="--exact", is_flag=True, help="Exact match"),
        "case": OptDef(flag="--case", is_flag=True, help="Case-sensitive search"),
        "exclude": OptDef(flag="--exclude", type=str, help="Exclude term from results"),
        "title": OptDef(
            flag="--title", is_flag=True, help="Search exploit titles only"
        ),
        "strict": OptDef(
            flag="--strict", is_flag=True, help="Require all terms to match"
        ),
    }

    input_flag = None
    file_flag = None
    output_flag = None
    json_flag = "--json"

    def _output_suffix(self) -> str:
        return ".json"

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        output_file: Path | None = None,
    ) -> list[Exploit]:
        data = self._read_json_output(stdout, output_file)
        if data is None:
            return []

        exploits = data.get("RESULTS_EXPLOIT", [])
        results: list[Exploit] = []

        for item in exploits:
            edb_id = str(item.get("EDB-ID", ""))
            results.append(
                Exploit(
                    name=item.get("Title", ""),
                    id=edb_id,
                    provider="exploit-db",
                    reference=f"https://www.exploit-db.com/exploits/{edb_id}"
                    if edb_id
                    else "",
                    tags=[
                        t
                        for t in [
                            item.get("Platform", ""),
                            item.get("Type", ""),
                        ]
                        if t
                    ],
                )
            )

        return results
