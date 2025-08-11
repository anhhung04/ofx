import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import ValidationError

# --- Setup a guaranteed clean test environment ---
SECRETS_DIR = Path("./temp_secrets")
ENV_FILE = Path(".env_test")
os.makedirs(SECRETS_DIR, exist_ok=True)

# Create a secret file
(SECRETS_DIR / "secret_from_file").write_text("file_value_123")

# Create a .env file with a different secret
ENV_FILE.write_text('SECRET_FROM_ENV="dotenv_value_456"')

print(f"⚙️  Created secret file at: {SECRETS_DIR.resolve() / 'secret_from_file'}")
print(f"⚙️  Created .env file at: {ENV_FILE.resolve()}")
print("-" * 20)


# --- Define the Settings Model ---
class AppSettings(BaseSettings):
    secret_from_file: str  # Should be loaded from secrets_dir
    secret_from_env: str  # Should be loaded from the .env file

    model_config = SettingsConfigDict(
        secrets_dir=str(SECRETS_DIR), env_file=str(ENV_FILE)
    )


# --- Attempt to load settings ---
try:
    print("🚀 Attempting to load settings...")
    settings = AppSettings()
    print("\n✅ SUCCESS! Settings loaded correctly.")
    print(f"   -> Loaded from file: '{settings.secret_from_file}'")
    print(f"   -> Loaded from .env: '{settings.secret_from_env}'")
except ValidationError as e:
    print("\n❌ FAILURE! Pydantic could not load the settings.")
    print(e)
finally:
    # --- Cleanup ---
    print("\n🧹 Cleaning up test environment...")
    os.remove(SECRETS_DIR / "secret_from_file")
    os.rmdir(SECRETS_DIR)
    os.remove(ENV_FILE)
