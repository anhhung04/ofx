from ofx.api.exploitation.webshell.connectors.template import TemplateConnector

def test_templates():
    connector = TemplateConnector()
    
    print("Testing PHP Obfuscation...")
    php = connector.generate("php", password="pass", obfuscate=True)
    print(f"PHP Preview: {php[:100]}...")
    assert "eval" in php or "base64" in php
    # With smart templates, tags should be preserved correctly
    assert "<?php" in php
    # Base64 encoded payload inside
    assert "base64_decode" in php

    print("\nTesting ASPX Obfuscation...")
    aspx = connector.generate("aspx", password="pass", obfuscate=True)
    print(f"ASPX Preview: {aspx[:100]}...")
    assert "<%@ Page" in aspx
    assert "System.Diagnostics" in aspx # Directive preserved
    # Check for obfuscation evidence
    assert "Convert.FromBase64String" in aspx or "System.Text.Encoding" in aspx

    print("\nTesting JSP Obfuscation...")
    jsp = connector.generate("jsp", password="pass", obfuscate=True)
    print(f"JSP Preview: {jsp[:100]}...")
    assert "<%@page" in jsp
    assert "java.util.Base64" in jsp or "String" in jsp

    print("\nTesting ASP Obfuscation...")
    asp = connector.generate("asp", password="pass", obfuscate=True)
    print(f"ASP Preview: {asp[:100]}...")
    assert "<%" in asp
    assert "Chr(" in asp or "Execute" in asp

if __name__ == "__main__":
    try:
        test_templates()
        print("\nAll Template Tests Passed!")
    except Exception as e:
        print(f"\nTest Failed: {e}")
        import traceback
        traceback.print_exc()
