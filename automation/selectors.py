from __future__ import annotations


AUTH_INPUT_SELECTORS = (
    'input[type="email"]',
    'input[name="email"]',
    'input[type="password"]',
    'input[name="password"]',
    'button:has-text("Log in")',
    'button:has-text("Sign in")',
)

MEMBERS_NAV_SELECTORS = (
    'a[href*="members"]',
    'button:has-text("Members")',
    'a:has-text("Members")',
    'button:has-text("Manage members")',
    'a:has-text("Manage members")',
)

MEMBER_SECTION_SELECTORS = (
    '[data-testid="members-page"]',
    '[data-testid="team-members-page"]',
    'main:has-text("Members")',
    'section:has-text("Members")',
)

MEMBER_COUNT_SELECTORS = (
    '[data-testid="members-count"]',
    '[data-testid="member-count"]',
    'text=/\\b\\d+\\s*members?\\b/i',
    'text=/\\bmembers?\\s*\\(\\d+\\)\\b/i',
)

MEMBER_ROW_SELECTORS = (
    '[data-testid="member-row"]',
    '[data-testid="team-member-row"]',
    'tr:has([href*="mailto:"])',
    'tr',
)

PENDING_ROW_SELECTORS = (
    '[data-testid="pending-invite-row"]',
    '[data-testid="invite-row"]',
    'tr:has-text("Pending")',
)

INVITE_BUTTON_SELECTORS = (
    'button:has-text("Invite members")',
    'button:has-text("Invite member")',
    'button:has-text("Invite")',
)

INVITE_DIALOG_SELECTORS = (
    '[role="dialog"]',
    '[data-testid="invite-members-dialog"]',
    '[data-testid="invite-dialog"]',
)

INVITE_EMAIL_INPUT_SELECTORS = (
    '[role="dialog"] input[type="email"]',
    '[role="dialog"] textarea',
    '[data-testid="invite-email-input"]',
    '[data-testid="invite-members-input"]',
)

INVITE_SUBMIT_SELECTORS = (
    '[role="dialog"] button:has-text("Send invite")',
    '[role="dialog"] button:has-text("Send invites")',
    '[role="dialog"] button:has-text("Invite")',
    '[data-testid="invite-submit-button"]',
)

SUCCESS_MESSAGE_SELECTORS = (
    'text=/invite sent/i',
    'text=/invitation sent/i',
    'text=/member invited/i',
    '[role="status"]',
    '[data-testid="toast"]',
)

DUPLICATE_HINT_SELECTORS = (
    'text=/already invited/i',
    'text=/already a member/i',
    'text=/pending invite/i',
    'text=/already exists/i',
)
