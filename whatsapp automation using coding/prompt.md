# Project: WhatsApp Food Delivery AI Agent

## 1. Your Role

Act as a senior automation engineer, backend developer, AI engineer, and technical mentor.

Build a complete, reliable, modular WhatsApp Food Delivery AI Agent in the currently opened project folder.

I am a beginner, so explain important technical decisions clearly and guide me through the implementation step by step. Do not assume that I know how to configure APIs, environment variables, webhooks, databases, or deployment.

We previously attempted to build this automation in n8n, but we encountered node configuration and webhook issues. We are now rebuilding it as a clean, code-based project using Antigravity.

**Do not build all five modules in one go. Implement and verify one module at a time.**

After completing each module:
1. Explain what was implemented.
2. List the files created or modified.
3. Give the exact commands to run in the terminal.
4. Run available tests and show their actual results.
5. Tell me how to verify the result manually.
6. Identify any missing configuration or credentials.
7. Wait for my confirmation before starting the next module.

Never claim that a feature works unless it has actually been tested or clearly identify it as untested.

---

## 2. Main Project Goal

Build an AI-powered WhatsApp assistant for a food delivery business.

Customers should be able to message the business on WhatsApp and receive helpful, natural responses.

The assistant should be able to:

- Receive incoming WhatsApp messages.
- Understand customer questions using an LLM.
- Read food items, prices, and availability from our existing inventory spreadsheet.
- Answer frequently asked questions using our existing FAQ spreadsheet.
- Collect and validate order details.
- Calculate order totals accurately using application code.
- Create and record orders in our existing orders spreadsheet.
- Confirm orders to customers through WhatsApp.
- Handle missing information, unavailable items, invalid requests, and API failures safely.
- Avoid duplicate orders when webhook events are retried.
- Log errors and provide clear debugging information.

Do not assume that an order is placed just because the AI says it is. An order is confirmed only after the required validation and successful persistence of the order record.

Do not invent inventory, prices, availability, delivery charges, business policies, or order IDs.

---

## 3. Technology and Architecture

First inspect the current computer environment and project folder. Recommend a simple, maintainable stack suitable for a beginner.

Preferred direction:
- Python backend using FastAPI.
- Official WhatsApp Business Platform Cloud API through HTTPS requests.
- Google Sheets integration using the Google Sheets API.
- An LLM provider that can be configured through environment variables.
- Automated tests using pytest.
- Local development with a publicly reachable HTTPS tunnel when webhook testing is required.

You may recommend a different stack only if you explain why it is materially better for this project.

Do not use n8n as the main application runtime. We are building a code-based application.

Keep the application modular. Separate webhook handling, AI logic, business rules, inventory access, FAQ access, order management, WhatsApp API communication, configuration, and tests.

Use official API documentation for the selected providers. Verify current endpoints, authentication requirements, request formats, and webhook requirements rather than relying on guesses or outdated examples.

---

## 4. Existing Google Sheets — Mandatory Requirement

I will place the spreadsheet files that I downloaded from our earlier n8n project inside the project's `data/` directory.

These are expected to include:
- Inventory sheet or export.
- FAQ sheet or export.
- Orders sheet or export, if I have downloaded it.

Before implementing spreadsheet integration:

1. Inspect the filenames, file types, worksheet names, column headers, and sample structure.
2. Do not overwrite, rename, delete, or replace my existing files.
3. Identify whether each file is an actual Google Sheets export, CSV, XLSX, or another format.
4. Explain the difference between a downloaded snapshot and a live Google Sheet.
5. Ask me for any missing files or clarification if necessary.
6. Create a field mapping for inventory, FAQs, and orders based on the actual files.
7. Do not invent column names when the real files are available.

**Important:** A downloaded CSV or XLSX file is only a local snapshot. Changes to it will not automatically update the original online Google Sheet.

For the real automation, use the Google Sheets API to read and write the original online spreadsheets when their spreadsheet IDs, permissions, and credentials are configured. Use the downloaded files for schema inspection and offline tests.

If I only have downloaded files and cannot yet provide access to the live Google Sheets, build a clearly labelled local test adapter first. Never claim that local file changes have updated Google Sheets.

If the inventory and FAQ data are in separate Google Sheets, support their separate spreadsheet IDs and worksheet/tab names.

Use an appropriate strategy for the orders sheet that prevents duplicate order records where possible.

---

## 5. Credentials and Secrets

I already have some of the required API keys, access tokens, phone number information, and account details from our earlier setup. I will provide them when required.

**Do not ask me to paste every credential at the beginning.** Request only the exact credential needed for the current implementation or test.

Possible configuration includes:

- WhatsApp access token.
- WhatsApp Phone Number ID.
- WhatsApp Business Account ID, if required for a specific operation.
- WhatsApp webhook verification token.
- LLM provider API key.
- Google Cloud service account credentials or another supported Google authentication method.
- Inventory, FAQ, and orders spreadsheet IDs.
- Worksheet/tab names.
- Public HTTPS webhook URL during testing.

Ask for missing values by their exact names and explain where to obtain them. Do not assume the account ID and phone number ID are interchangeable.

Security rules:
- Never hardcode credentials in source code.
- Never commit real secrets to Git.
- Create `.env.example` containing placeholders only.
- Add `.env`, service-account JSON files, private keys, logs containing sensitive data, and other secrets to `.gitignore`.
- Load configuration from environment variables using a suitable configuration library.
- Never print full access tokens, API keys, or private credentials in terminal output.
- If credentials are shared accidentally in logs, mask them in displayed output.
- Do not upload credentials or private keys to external services.
- Never expose secrets in AI prompts, customer responses, or error messages.

If I need to create a local `.env` file, provide the exact variable names and explain how to enter the values securely. Do not create a real `.env` with fabricated credentials.

---

# 6. Five-Module Development Plan

## MODULE 1 — Project Foundation and Configuration

Goal: Establish a clean, runnable application before connecting external services.

Tasks:
1. Inspect the current root folder and the spreadsheet files I have added.
2. Check Python and package-manager availability.
3. Create a virtual environment.
4. Establish the project structure.
5. Create dependency and configuration files.
6. Create `.env.example`, `.gitignore`, and `README.md`.
7. Implement typed configuration loading and validation.
8. Add a health-check endpoint using FastAPI.
9. Add structured logging with secrets and sensitive customer data redacted.
10. Add the initial pytest test suite.
11. Add a startup check that reports missing configuration variable names without revealing values.

Suggested structure:

WhatsApp-Food-Delivery-AI/
- src/
  - app/
    - main.py
    - config.py
    - logging_config.py
    - api/
    - services/
    - integrations/
    - models/
    - repositories/
    - utils/
- tests/
- data/
- scripts/
- .env.example
- .gitignore
- README.md
- requirements.txt
- pyproject.toml, if useful

Adjust the structure when necessary, but keep it understandable.

Verification:
- The virtual environment activates successfully.
- Dependencies install successfully.
- The application starts locally.
- A health-check endpoint returns a successful response.
- Configuration validation tests pass.
- No external API keys are required for the basic health check.

At the end, provide the actual test results and stop. Wait for my confirmation before Module 2.

## MODULE 2 — WhatsApp Cloud API and Webhooks

Goal: Receive and send real WhatsApp messages safely.

Tasks:
1. Implement the WhatsApp webhook verification endpoint using the official verification handshake.
2. Implement an incoming-message webhook endpoint.
3. Parse incoming text messages safely.
4. Handle message IDs, sender numbers, timestamps, and supported message types.
5. Ignore or safely handle unsupported message types.
6. Acknowledge webhook requests promptly and process messages without blocking the webhook response unnecessarily.
7. Implement a WhatsApp Cloud API client for sending text messages.
8. Use the configured Phone Number ID in the correct API endpoint.
9. Handle authentication errors, rate limits, network errors, and invalid recipients.
10. Implement idempotency for incoming webhook events so retries do not trigger duplicate processing.
11. Redact sensitive information from logs.
12. Add unit tests using mocked API responses.

Verification:
- Test webhook verification locally.
- Test incoming message parsing with sample payloads.
- Test outbound message formatting using mocks before making a real API call.
- Ask me for the WhatsApp credentials required for a live test.
- Help me expose the local server through a public HTTPS tunnel if necessary.
- Explain the distinction between test webhook URLs and production webhook URLs.
- Verify that the webhook is registered and reachable before claiming incoming messages work.
- Send a real test message only after configuration is checked and I approve the test.

Important:
A local URL such as localhost cannot be reached directly by Meta's servers. Never claim that the incoming webhook works until a public HTTPS endpoint and the required Meta webhook configuration have been verified.

Stop after the module's verification and wait for my confirmation.

## MODULE 3 — Google Sheets Integration and Business Logic

Goal: Connect the application to our existing business data.

Tasks:
1. Inspect the real spreadsheet schema and use its actual column names.
2. Implement a reusable Google Sheets client.
3. Read inventory data from the existing online inventory sheet.
4. Read FAQ data from the existing online FAQ sheet.
5. Validate item names, quantities, prices, and availability.
6. Implement order calculations in normal application code, not through an LLM's arithmetic.
7. Implement order creation using the actual orders-sheet schema.
8. Validate required order fields before writing.
9. Add a unique order ID generated by the application.
10. Store order status, timestamps, item details, quantities, unit prices, and totals using the actual schema and supported fields.
11. Use safe retry and duplicate-prevention logic.
12. Avoid treating a successful read as proof that a write succeeded.
13. Handle Google authentication, missing sheets, permission errors, quota errors, and invalid ranges.
14. Add tests with mocked Sheets responses and local fixture data.

Verification:
- Confirm inventory data can be read.
- Confirm FAQ data can be read.
- Test item lookup and quantity validation.
- Test order totals against known examples.
- Test order writing in a controlled test environment before using the production orders sheet.
- Ask me for spreadsheet IDs, worksheet names, and Google credentials only when needed.
- Never create fake records in my real orders sheet without my explicit approval.

If the orders sheet cannot safely be tested without affecting real data, explain the risk and provide a mock or dedicated test worksheet option.

Stop after verification and wait for my confirmation.

## MODULE 4 — AI Agent and Conversation Management

Goal: Build the conversational intelligence layer.

Tasks:
1. Create a dedicated AI service independent of the WhatsApp API code.
2. Configure the selected LLM provider through environment variables.
3. Ask me which provider and model I want to use if the available credentials do not establish this.
4. Use the existing inventory and FAQ services as trusted data sources.
5. Design clear system instructions for a food delivery assistant.
6. Support customer questions, menu browsing, availability checks, ordering, and order clarification.
7. Maintain conversation state per customer using an appropriate storage mechanism.
8. Keep conversation history isolated between customers.
9. Do not allow the LLM to invent prices, items, availability, delivery policies, or order confirmations.
10. Use typed request/response models and controlled service functions for business operations.
11. Validate all AI-proposed actions in application code.
12. Ask follow-up questions when information required for an order is missing.
13. Handle ambiguous requests, prompt injection, unexpected model output, timeouts, and model-provider failures.
14. Add limits for message size, context history, and API usage.
15. Add tests for common conversations and failure cases.

Order workflow should generally be:
- Customer expresses intent to order.
- Assistant identifies the requested items.
- Application checks actual inventory and prices.
- Assistant asks for missing information.
- Customer reviews the final order summary.
- Application validates the final order.
- The order is written to the orders sheet.
- Assistant confirms the order only after successful persistence.

Collect only the customer details genuinely needed for fulfilment. Do not collect payment card details or sensitive information through the chat.

Verification:
- Test FAQs.
- Test menu and price questions.
- Test unavailable items.
- Test incomplete orders.
- Test quantity and total calculations.
- Test separate customer conversations.
- Test model errors.
- Use mocked services before connecting the AI to live WhatsApp messages.

Ask me for the LLM API key only when the module is ready for a real model test.

Stop after verification and wait for my confirmation.

## MODULE 5 — Full Integration, End-to-End Testing, and Runbook

Goal: Integrate every verified module into the complete automation.

Tasks:
1. Connect the WhatsApp webhook, AI service, inventory, FAQ service, order service, and outbound messaging client.
2. Establish a clear message-processing flow.
3. Add timeouts and bounded retries.
4. Prevent duplicate order creation from repeated webhook events.
5. Ensure the customer receives a clear error or recovery message if processing fails.
6. Avoid exposing stack traces, credentials, internal prompts, or private business data to customers.
7. Add appropriate health checks and operational logs.
8. Create end-to-end tests with mocked external services.
9. Provide a separate, controlled live-test procedure.
10. Document installation, configuration, startup, shutdown, and troubleshooting.
11. Explain how to run the project after restarting the computer.
12. Document webhook setup, tunnel usage, and production deployment considerations.
13. Provide a final project tree and a list of implemented features versus remaining limitations.

Verification scenarios:
- Customer sends a greeting.
- Customer asks for the menu.
- Customer asks a question answered by the FAQ sheet.
- Customer requests an unavailable item.
- Customer submits an incomplete order.
- Customer confirms a valid order.
- The order is successfully recorded in the correct sheet.
- The customer receives a confirmation only after successful order creation.
- A duplicate webhook event does not create another order.
- The Google Sheets API fails.
- The LLM API fails.
- The WhatsApp send request fails.
- Two customers message at approximately the same time.

Do not run destructive tests against the real business data. Use mocks or an explicitly approved test worksheet where appropriate.

At the end, provide a final acceptance checklist and exact startup instructions.

---

## 7. Coding Standards

- Use clear, descriptive filenames and function names.
- Keep individual modules focused.
- Add type hints to Python functions.
- Use Pydantic models where they improve validation.
- Separate API routes from business logic and external integrations.
- Never put all application logic in one large file.
- Avoid unnecessary dependencies.
- Use asynchronous code where it is beneficial and properly supported.
- Add meaningful exception handling.
- Never silently swallow important errors.
- Use deterministic business rules for pricing and order validation.
- Use mocked external APIs in automated tests.
- Keep the README beginner-friendly.
- Do not modify files outside the currently opened project directory unless I approve.
- Do not install unrelated tools or globally change my computer configuration without explaining the action and receiving my approval when needed.

If you discover a technical problem, explain its cause and offer the smallest safe fix. Do not rewrite working modules unnecessarily.

## 8. How You Must Work With Me

I want a guided implementation, not a giant code dump.

For each module, use this sequence:

**Step A:** Inspect and explain what needs to be built.

**Step B:** Tell me which files you will create or modify.

**Step C:** Implement only the current module.

**Step D:** Run tests and show actual outputs.

**Step E:** Explain how I can verify the result.

**Step F:** Ask me to confirm whether the verification succeeded.

Only after I confirm should you start the next module.

When you need a credential, ask for its exact name and explain what it is used for. Do not request secrets earlier than necessary.

If you need a credential, use a local environment variable or a secure local credential file. Never ask me to commit secrets to the repository. Prefer entering the value directly into my local environment rather than pasting it into source code or committing it to the project.

If a live API test requires a real message or modifies business data, explain exactly what will happen and ask for my approval first.

If a step fails, stop and help me debug that specific step. Do not continue to the next module with an unresolved failure.

---

## 9. Start Now — Module 1 Only

Begin with Module 1.

First inspect the currently opened project directory and the files inside `data/`. Check the available environment and identify the existing spreadsheet schemas.

If the folder is empty or the spreadsheets are not present, tell me exactly what is missing and wait for me to add them.

Then create the project foundation, install only the necessary dependencies, implement the health-check endpoint, and run the tests.

Do not implement Module 2 or request WhatsApp, Google, or LLM secrets yet.

At the end, provide:
1. What was completed.
2. The final file structure.
3. Exact commands to run the application.
4. Actual test results.
5. Any remaining Module 1 issues.
6. One clear question asking me to confirm the verification before proceeding.