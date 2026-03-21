---
name: Checkout Flow E2E Test (QA)
description: End-to-end form completion (e-commerce/SaaS) requiring strict verify_ui_state after every single interaction.
namespace: qa/testing
trigger_patterns:
  - "test the checkout flow on \\{url\\}"
  - "run an e2e test for the shopping cart"
  - "verify I can complete a purchase on \\{app_name\\}"
  - "automate the payment form"
parameters:
  url:
    type: string
    description: Optional target URL for the cart or checkout page.
  app_name:
    type: string
    description: Optional target application.
  test_data:
    type: string
    description: Optional JSON string or description of the mock data to use (e.g., fake credit card, shipping address).
---

# 🧠 Expert Guide (心法)
This SOP defines the rigorious, state-machine-like execution required for End-to-End (E2E) testing of high-value conversion flows (SignUp, Checkout, Onboarding), preventing the agent from blindly clicking through broken states.

## Setup & Preconditions
1. Navigate to the start of the `url` funnel.
2. If `test_data` is missing, you MUST generate mock data (e.g., Jane Doe, 123 Main St, 4242-4242-4242-4242) before beginning.

## Phase 1: Pre-Checkout (Cart Validation)
1. **Analyze Scene**: Use `analyze_image` to check if items are in the cart.
2. **Execute Add (If Empty)**: If the cart is empty, navigate to a product page and click "Add to Cart".
3. **Pivotal State Check**: You MUST call `verify_ui_state(target_text="Proceed to Checkout", target_element="Button")`. Do not proceed until this passes.
4. **Transition**: Click the "Proceed to Checkout" button.

## Phase 2: Form Completion (The Gauntlet)
This phase requires extreme discipline. Treat each input field as a discrete step.

1. **Locate Target Field**: Find the specific input (e.g., "Email Address").
2. **Execute Input**: `click` the field, then `keyboard` type the mock data.
3. **Handle Interstitials**:
   *   If a "Subscribe to Newsletter" modal pops up, you MUST identify the "No Thanks" or "X" button and click it to clear the DOM layer.
   *   If an Address Autocomplete dropdown appears, you MUST either click the first suggestion or hit `Escape` to bypass it.
4. **Repeat**: Repeat Steps 1-3 for Shipping Address, Billing Address, and Payment Details.

## Phase 3: Final Verification & Submission
1. **Verify State**: Before clicking "Place Order", take a screenshot. Ensure no red validation error messages (e.g., "Invalid CVV") are visible.
2. **Submit**: Click the final "Place Order" or "Pay Now" button.
3. **Wait for Network**: Wait 5-10 seconds. E2E payment flows are slow.
4. **Final Assertion (Critical)**: Capture a new screenshot. You MUST call `verify_ui_state(target_text="Thank you", target_element="Heading")` or similar confirmation text.
5. **Report**: Output the test result (PASS/FAIL) and the final Order Confirmation Number if found.

## 🛟 Recovery Strategy
- **Unexpected Captcha**: If a Stripe or payment captcha appears, immediately transition to the `browser/mac/bypass_captcha_login` SOP.
- **Form Submit Fails Silently**: If clicking "Place Order" does nothing, you must use `analyze_image` specifically looking for disabled button states or hidden required fields (e.g., "I agree to Terms & Conditions" checkbox).
