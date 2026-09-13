"""Run the agent end to end and print the structured result."""

import json
import sys

from agent import run_agent

customer_id = sys.argv[1] if len(sys.argv) > 1 else "C001"
result = run_agent(customer_id)

print("\n" + "=" * 74)
print("STRUCTURED OUTPUT")
print("=" * 74)
print(json.dumps(result, indent=2))
