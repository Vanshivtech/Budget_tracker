import re

with open('frontend/index.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update modal-close buttons
content = re.sub(
    r'class="modal-close"([^>]*)>',
    lambda m: f'class="modal-close"{m.group(1)} data-tooltip="Close without saving">' if 'data-tooltip' not in m.group(0) else m.group(0),
    content
)

# 2. Add Udhar button tooltip
content = content.replace('id="btn-add-udhar-trigger"', 'id="btn-add-udhar-trigger" data-tooltip="Record money you lent or borrowed"')

# 3. Add Save/Submit button tooltips if missing
replacements = [
    ('id="export-submit-btn"', 'id="export-submit-btn" data-tooltip="Generate and download statement"'),
    ('id="recurring-save-btn"', 'id="recurring-save-btn" data-tooltip="Save recurring bill"'),
    ('id="split-save-btn"', 'id="split-save-btn" data-tooltip="Save split expense across group"'),
    ('id="add-bill-save-btn"', 'id="add-bill-save-btn" data-tooltip="Upload and attach receipt file"'),
    ('id="clear-confirm-btn"', 'id="clear-confirm-btn" data-tooltip="Confirm and execute data clearing"'),
    ('id="expense-save-btn"', 'id="expense-save-btn" data-tooltip="Save this expense to your tracker"'),
    ('id="income-save-btn"', 'id="income-save-btn" data-tooltip="Save income entry"'),
    ('id="bulk-delete-action-btn"', 'id="bulk-delete-action-btn" data-tooltip="Permanently delete selected transactions"'),
    ('id="budget-add-save-btn"', 'id="budget-add-save-btn" data-tooltip="Save category spending budget"'),
    ('id="udhar-save-btn"', 'id="udhar-save-btn" data-tooltip="Save udhar lending or borrowing entry"'),
    ('id="goal-save-btn"', 'id="goal-save-btn" data-tooltip="Save savings goal"'),
    ('id="contrib-save-btn"', 'id="contrib-save-btn" data-tooltip="Record contribution to savings goal"'),
    ('id="rec-edit-save-btn"', 'id="rec-edit-save-btn" data-tooltip="Update recurring bill details"'),
    ('id="simple-confirm-btn"', 'id="simple-confirm-btn" data-tooltip="Confirm and proceed with this action"')
]

for old_str, new_str in replacements:
    if old_str in content and 'data-tooltip' not in content[content.find(old_str)-10:content.find(old_str)+80]:
        content = content.replace(old_str, new_str)

with open('frontend/index.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated index.html tooltips successfully')
