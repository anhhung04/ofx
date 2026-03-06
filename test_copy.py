from pydantic import BaseModel, Field

class RunContext(BaseModel):
    envs: dict[str, str] = Field(default_factory=dict)
    vars: dict[str, dict] = Field(default_factory=dict)

ctx = RunContext(envs={"foo": "bar"}, vars={"fleet": {"fleet_input_file": "test.txt"}})

ctx_copy = ctx.model_copy(deep=True)
ctx_copy.envs["foo"] = "baz"

ctx_copy.vars["fleet"]["fleet_input_file"] = "new.txt"

print("Original envs:", ctx.envs)
print("Copy envs:", ctx_copy.envs)

print("Original vars:", ctx.vars)
print("Copy vars:", ctx_copy.vars)

