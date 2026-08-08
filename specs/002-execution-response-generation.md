Problem:
Capability execution currently returns basic or vague text responses. When a
business operation cannot proceed because information is missing, invalid, or
ambiguous, the customer is not consistently given a clear next question.

Desired outcome:
After every planner command is executed, the system should generate one clear,
customer-facing response from the structured execution outcome. When further
customer information is required, it should ask one precise follow-up question.

Constraints:
- Preserve planner → command → handler → capability flow.
- Add a ResponseNode after ExecuteNode; do not make it a business-decision node.
- Capabilities/domain services remain the authority for validation, result
  status, missing information, and allowed options.
- The ResponseNode only formats/presents structured approved data.
- It must never invent products, prices, quantities, availability, or business
  outcomes.
- It must not modify CommerceSession or execute capabilities.
- Keep response generation separate from LangGraph-independent domain logic.
- Preserve checkpoint and transient-state serialization rules.

Acceptance criteria:
- A successful capability outcome produces a concise useful customer response.
- A missing required value produces one clear follow-up question.
- An invalid input produces a specific correction request.
- A product-not-found outcome asks an appropriate clarification.
- The node cannot expose arbitrary internal exceptions or unapproved data.
- Existing greeting, search, and select-product flows continue to work.