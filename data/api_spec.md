# Mock ERP / Accounts Payable API Specification

Base URL: `http://127.0.0.1:8000` (or configured via environment)

All authenticated endpoints require an `Authorization: Bearer <token>` header.

---

### 1. Authentication
* **POST `/auth/login`**
  - Request body (JSON):
    ```json
    { "username": "admin", "password": "secret_token_pass" }
    ```
  - Response (200 OK):
    ```json
    { "access_token": "eyJhbG...", "token_type": "Bearer", "expires_in_seconds": 3600 }
    ```

---

### 2. Vendors
* **GET `/vendors`**
  - Returns list of registered vendors.

---

### 3. Invoices
* **POST `/invoices`**
  - Create a new invoice record.
  - Request body (JSON):
    ```json
    {
      "vendor": "Acme Cloud Solutions",
      "amount": 14250.00,
      "due_date": "2026-11-30",
      "currency": "USD",
      "notes": "Optional notes"
    }
    ```
  - Constraints:
    - `due_date` **MUST** follow strict `YYYY-MM-DD` ISO format. Other formats return `422 Unprocessable Entity`.
    - `amount` must be a positive number.
    - If identical vendor, amount, and due_date exists, returns `409 Conflict`.
  - Response (201 Created):
    ```json
    { "id": 1, "vendor": "Acme Cloud Solutions", "amount": 14250.0, "currency": "USD", "due_date": "2026-11-30", "status": "PENDING", ... }
    ```

* **GET `/invoices`**
  - Query parameters:
    - `vendor` (string, optional): search by vendor name
    - `status` (string, optional): PENDING, APPROVED, PAID
  - Response (200 OK): array of invoice objects.

* **GET `/invoices/{id}`**
  - Retrieve single invoice by primary key. Used for verification.
  - Response: 200 OK or 404 Not Found.

* **PATCH `/invoices/{id}`**
  - Update fields (`amount`, `due_date`, `status`, `notes`).
  - NOTE: Destructive/modification action - company policy requires human approval.

* **DELETE `/invoices/{id}`**
  - Deletes an invoice.
  - NOTE: Destructive action - company policy requires human approval.

---

### 4. Discovery
* **GET `/openapi.json`**
  - Standard OpenAPI specification exposing all schemas, paths, and methods.
