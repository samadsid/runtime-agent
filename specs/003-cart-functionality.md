Cart Functionality Specification

Status: Approved for implementationScope: In-memory cart vertical slice for the AI Commerce Agent

1. Purpose

Enable a customer to add the currently selected product to their cart afterproviding a quantity. The cart is session-scoped and remains in memory for thismilestone.

This specification preserves the frozen architecture:

Planner → Command → Handler → Capability → Approved execution outcome → Response Node

The runtime remains generic. Cart business rules belong in the commerce domainand commerce capabilities.

2. Customer Flow

Customer: I want chicken breast
→ search_product / select_product
→ “Selected Chicken Breast. How much would you like to order?”

Customer: 2 kg
→ add_to_cart
→ “Added 2 kg Chicken Breast to your cart.”

The customer may also explicitly provide product and quantity together in alater iteration. That is outside this first cart slice.

3. Scope

Included

Session-scoped in-memory cart state.

Adding the selected product with a valid quantity.

Updating the quantity when the same product is added again.

Viewing cart contents.

Removing a cart item by its displayed ordinal.

Grounded, approved execution outcomes for every cart action.

Planner routing rules for quantity after a product has been selected.

Excluded

Checkout and order creation.

Payment, delivery address, taxes, discounts, and inventory reservation.

PostgreSQL persistence.

Cart sharing across sessions or channels.

Product variants and modifiers.

Changing LangGraph topology or the generic runtime contracts.

4. Domain Model

Create a commerce-domain CartItem value model.

Field

Type

Rule

product

Product

The catalog product added by the customer.

quantity

Decimal

Must be greater than zero.

Add the following field to CommerceSession:

Field

Type

Default

cart_items

tuple[CartItem, ...]

Empty tuple

selected_product represents the product currently being discussed. It is notthe cart. A product is added to the cart only after a successfuladd_to_cart execution.

5. Capabilities

5.1 add_to_cart

Purpose: Add the currently selected product with a supplied quantity.

Arguments:

Argument

Type

Validation

quantity

decimal number

Required and greater than zero.

Preconditions:

CommerceSession.selected_product exists.

The quantity is valid.

Behaviour:

Read the selected product from the session.

Validate the supplied quantity.

If the product is not already in cart_items, add a CartItem.

If the same product is already in cart_items, replace its quantity withthe newly supplied quantity for this milestone.

Return the updated session and a success outcome.

Success outcome:

Added {quantity} {unit} {product_name} to your cart.

The response outcome must use only approved values from the selected productand validated quantity.

Missing selected product outcome:

Please select a product before adding it to your cart.

Follow-up: ask one product-search or product-selection question, based on theavailable session context.

Invalid quantity outcome:

Please provide a quantity greater than zero.

Follow-up: ask exactly one quantity question.

5.2 view_cart

Purpose: Show the current session cart.

Arguments: None.

Behaviour:

If the cart is empty, return an approved empty-cart fragment and a conciseproduct-search follow-up.

Otherwise, return one approved item fragment per cart item in display order.

Each displayed item must have a 1-based ordinal so it can later be removed.

Example response meaning:

Your cart:
1. Chicken Breast — 2 kg

Prices and totals are excluded until the checkout slice.

5.3 remove_from_cart

Purpose: Remove one cart item using its 1-based displayed ordinal.

Arguments:

Argument

Type

Validation

ordinal

integer

Required, 1-based, must identify a current cart item.

Behaviour:

Remove the item identified by the ordinal.

Return an approved confirmation outcome.

For missing or invalid ordinals, return available cart options as approvedoptions and ask one focused clarification question.

6. Planner Rules

Add these rules to the commerce capability guidance:

- When a product is selected and the customer provides a quantity, execute
  `add_to_cart` with that quantity.
- Do not execute `add_to_cart` when no selected product exists.
- When the customer asks to see their cart, execute `view_cart`.
- When the customer asks to remove an item using a valid cart ordinal, execute
  `remove_from_cart` with that ordinal.
- Never interpret a cart ordinal as a product-search-result ordinal.

Quantity parsing is planner work; quantity validation remains deterministic inadd_to_cart.

7. Session State Rules

Recent product results remain available for product selection.

Cart items remain available for cart viewing and removal.

selected_product may remain set after adding to the cart; it is useful forsubsequent quantity changes, but it must not be treated as proof that theproduct is already in the cart.

All session changes must use immutable session updates throughmodel_copy(update=...).

8. Acceptance Criteria

After selecting Chicken Breast and sending 2 kg, the planner selectsadd_to_cart with quantity 2.

The capability stores Chicken Breast with quantity 2 in the session cart.

The response is grounded in the approved outcome and asks no extra questionafter a successful add.

Sending show my cart returns the cart item with a 1-based display number.

Sending remove 1 removes the first cart item, not a recent product-searchresult.

Invalid, missing, zero, or negative quantities do not modify the cart.

No cart, order, payment, or database business logic is added to runtime/.

Existing greeting, search, product selection, response generation, anddeterministic response fallback behaviour continue to work.

9. Required Tests

add_to_cart adds a selected product with a valid quantity.

add_to_cart replaces the quantity for an existing cart product.

add_to_cart rejects a missing selected product.

add_to_cart rejects missing, invalid, zero, and negative quantities.

view_cart returns the empty-cart outcome.

view_cart returns ordered cart items.

remove_from_cart removes a valid ordinal.

remove_from_cart rejects missing and invalid ordinals without changing thecart.

Planner routing test: selected product + 2 kg routes to add_to_cart.

Planner routing test: show my cart routes to view_cart.

10. Deferred Follow-up

After this slice is verified, the next slice is checkout: review cart, collectdelivery details, create an order, and confirm it. PostgreSQL persistence shouldbe introduced when cart and order state need to survive process restarts.