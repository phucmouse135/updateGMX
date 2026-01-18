# Instagram Auto 2FA Tool

This tool automates the process of enabling two-factor authentication (2FA) for Instagram accounts.

## Error Codes

This section explains the meaning of the error codes that may appear in the "Note" column of the application.

- **`LOGIN_FAILED`**: The cookie provided is invalid or expired, and the login to Instagram failed.
- **`INSTAGRAM_BLOCKED`**: Instagram has temporarily blocked the action, likely due to security reasons (e.g., unfamiliar device). Please try again later.
- **`ALREADY_2FA_ON`**: Two-factor authentication is already enabled for the account.
- **`NO_IG_ACCOUNT_FOUND`**: No Instagram account was found on the account selection page.
- **`ACCOUNT_SELECTION_STUCK`**: The process is stuck on the account selection page.
- **`MAIL_CODE_FETCH_FAILED`**: The tool failed to retrieve the verification code from the email. This could be due to incorrect email credentials or a delay in receiving the email.
- **`WRONG_EMAIL_CODE`**: The email verification code entered was incorrect.
- **`SECRET_KEY_NOT_FOUND`**: The 2FA secret key could not be found on the page.
- **`WRONG_OTP_CODE`**: The one-time password (OTP) from the authenticator app was incorrect. Please check your device's time and try again.
- **`OTP_TIMEOUT`**: The process timed out while waiting for the OTP confirmation screen.
- **`CRITICAL_ERROR`**: A critical error occurred, and the 2FA setup could not be completed.