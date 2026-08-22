Approved execution outcome:

{{execution_outcome}}

Latest customer message:

{{customer_message}}

Write the grounded customer response in the customer's own language and chat
style.

Before returning the structured response:

1. Copy every ID from `fragments` into `fragment_ids`, in the same order.
2. Copy only `follow_up.id` into `follow_up_id` when `follow_up` is present.
3. Never place `follow_up.id` inside `fragment_ids`.
4. Use only approved information in `message`.
5. If a follow-up is provided, include exactly one question based only on that
   approved follow-up.
6. Use the semantic layout supplied by the outcome, or infer the smallest valid
   semantic layout from its fragment kinds and selectable options.

Return the response using these fields:

- `layout`
- `fragment_ids`
- `follow_up_id`
- `message`
