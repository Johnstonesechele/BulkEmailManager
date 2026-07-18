# Changelog - Bulk Email Manager

## February 10, 2026

### Features Added

#### 1. Multiple CSV Files Support
- **New Button**: Added "Load Multiple CSVs" button in the Contacts tab
- **Functionality**: 
  - Users can now select and load multiple CSV files at once using Ctrl/Shift selection
  - All selected CSV files are merged into a single contact list
  - Automatic duplicate detection and removal based on email addresses
  - Validation that each CSV file contains the required "Emails" column
  - Files without "Emails" column are skipped with a warning message
  - Detailed logging shows:
    - Number of CSV files loaded
    - Total number of contacts
    - Number of duplicates removed (if any)

#### 2. Increased Daily Email Limit
- **Previous Limit**: 450 emails per day
- **New Limit**: 3000 emails per day
- **Impact**: Users can now send significantly more emails in a single campaign
- **Files Updated**: 
  - `bulk_email.py` - Line 230
  - `version2.py` - Line 229

### Technical Details

**Files Modified:**
1. `bulk_email.py`
   - Updated `BulkEmailSender.send_bulk_emails()` method parameter `max_emails_per_day` from 450 to 3000
   - Added `load_multiple_btn` button to ContactsTab
   - Added `load_multiple_csvs()` method with duplicate detection

2. `version2.py`
   - Updated `BulkEmailSender.send_bulk_emails()` method parameter `max_emails_per_day` from 450 to 3000
   - Added `load_multiple_btn` button to ContactsTab
   - Added `load_multiple_csvs()` method with duplicate detection

### Usage Instructions

**To Load Multiple CSV Files:**
1. Open the Contacts tab
2. Click the "Load Multiple CSVs" button
3. Select multiple CSV files using Ctrl+Click or Shift+Click
4. Click "Open"
5. The application will:
   - Load all valid CSV files
   - Combine them into one list
   - Remove duplicate email addresses
   - Display the total number of contacts

**Note**: When multiple CSV files are loaded, the "Save CSV" button will prompt for a new filename since there's no single source file to save back to.
