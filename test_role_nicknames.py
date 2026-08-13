import ast
from pathlib import Path

source = Path(__file__).parent.joinpath("cogs", "role_nicknames.py").read_text()
tree = ast.parse(source)
function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "leading_emoji")
module = ast.Module(body=[ast.Import(names=[ast.alias(name="unicodedata")]), function], type_ignores=[])
module = ast.fix_missing_locations(module)
namespace = {}
exec(compile(module, "role_nicknames.py", "exec"), namespace)
leading_emoji = namespace["leading_emoji"]

assert leading_emoji("✅ Member") == "✅"
assert leading_emoji("🔗 Moderator") == "🔗"
assert leading_emoji("Member") is None
assert leading_emoji("  🛡️ Admin") == "🛡️"
print("role nickname emoji tests passed")
