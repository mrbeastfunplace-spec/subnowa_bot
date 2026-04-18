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
    'button:has-text("Invite team members")',
    'a:has-text("Invite team members")',
    'button:has-text("Invite")',
    'a:has-text("Invite")',
    'button:has-text("team")',
    'button:has-text("member")',
)

MEMBER_SECTION_SELECTORS = (
    '[data-testid="members-page"]',
    '[data-testid="team-members-page"]',
    '[role="dialog"]:has(input[type="email"])',
    'aside:has(input[type="email"])',
    'section:has(input[type="email"])',
    'main:has-text("Invite team members")',
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
    'button:has-text("Invite team members")',
    'a:has-text("Invite team members")',
    'text=Invite team members',
    'button:has-text("Invite members")',
    'button:has-text("Invite member")',
    'button:has-text("Invite")',
    'a:has-text("Invite")',
    'text=Invite',
    'button:has-text("team")',
    'button:has-text("member")',
)

INVITE_DIALOG_SELECTORS = (
    '[role="dialog"]',
    '[data-testid="invite-members-dialog"]',
    '[data-testid="invite-dialog"]',
    '[data-testid*="invite"]:has(input[type="email"])',
    'aside:has(input[type="email"])',
    'section:has(input[type="email"])',
)

INVITE_EMAIL_INPUT_SELECTORS = (
    '[role="dialog"] input[type="email"]',
    '[role="dialog"] input[placeholder*="email" i]',
    '[role="dialog"] input[aria-label*="email" i]',
    'input[type="email"]',
    'input[placeholder*="email" i]',
    'input[aria-label*="email" i]',
    'input[name*="email" i]',
    '[role="dialog"] textarea',
    '[data-testid="invite-email-input"]',
    '[data-testid="invite-members-input"]',
)

INVITE_SUBMIT_SELECTORS = (
    '[role="dialog"] button:has-text("Send invite")',
    '[role="dialog"] button:has-text("Send invites")',
    '[role="dialog"] button:has-text("Invite")',
    '[role="dialog"] button:has-text("Send")',
    '[role="dialog"] button:has-text("Add")',
    'button:has-text("Send invite")',
    'button:has-text("Send invites")',
    'button:has-text("Invite")',
    'button:has-text("Send")',
    'button:has-text("Add")',
    '[data-testid="invite-submit-button"]',
)

SUCCESS_MESSAGE_SELECTORS = (
    'text=/invite sent/i',
    'text=/invitation sent/i',
    'text=/member invited/i',
    'text=/invited/i',
    'text=/added/i',
    '[role="status"]',
    '[data-testid="toast"]',
)

DUPLICATE_HINT_SELECTORS = (
    'text=/already invited/i',
    'text=/already a member/i',
    'text=/pending invite/i',
    'text=/already exists/i',
)
