# CSV Import Troubleshooting Guide

## Expected CSV Format
```
User name,User ID,Phone number
john_doe,123456789,+1234567890
@jane_smith,987654321,+9876543210
mike_wilson,555444333,+5554443333
```

## Common Issues

### 1. File Format
- Make sure the file is saved as CSV (comma-separated values)
- Use UTF-8 encoding
- No special characters in cell content that break CSV structure

### 2. Required Columns
- Header must be exactly: `User name,User ID,Phone number`
- At least one field per row must be filled
- User ID should be numeric (if provided)

### 3. Browser Console Check
To debug the issue:
1. Open browser Developer Tools (F12)
2. Go to Console tab
3. Try importing CSV file
4. Look for error messages or debug logs

Expected console output:
```
CSV upload function called
Selected file: File object
FileReader started
Adding campaign user: {username: "john_doe", user_id: "123456789", phone: "+1234567890", priority: 1}
```

### 4. Create Test CSV File
Create a simple test file with this content:
```
User name,User ID,Phone number
test_user,123456789,+1234567890
```

### 5. Check File Input Element
- Make sure the hidden file input is correctly triggered
- Verify file is actually selected (check file size in console)

## Manual Debug Steps
1. Click "Import CSV/XLS" button
2. Select a properly formatted CSV file
3. Check browser console for debug messages
4. If no messages appear, there may be a JavaScript error preventing execution

## Contact Support
If the issue persists, provide:
- Browser and version
- CSV file content (first few rows)
- Any console error messages

## Excel File Support (NEW)

### Supported Excel Formats
- .xlsx (Excel 2007+)  
- .xls (Excel 97-2003)
- .xlsm (Excel with macros)

### Excel File Requirements
1. **Column Structure**: Same as CSV
   ```
   User name | User ID   | Phone number
   john_doe  | 123456789 | +1234567890
   jane_doe  | 987654321 | +9876543210
   ```

2. **First Worksheet**: System uses the first worksheet in the file

3. **Data Types**: 
   - User name: Text
   - User ID: Number (can be formatted as text)
   - Phone number: Text (with + prefix)

### Creating Excel Template
1. Open Excel or Google Sheets
2. Create headers: `User name`, `User ID`, `Phone number`
3. Add your user data
4. Save as .xlsx format

### Excel vs CSV
- **Excel**: Better formatting, data validation, easier editing
- **CSV**: Smaller file size, universal compatibility
- **Both**: Same import functionality, same column requirements

### Common Excel Issues
1. **Wrong Worksheet**: Make sure data is on the first sheet
2. **Number Formatting**: User IDs should not have scientific notation (use text format)
3. **Empty Rows**: System skips empty rows automatically
4. **Special Characters**: Use UTF-8 compatible characters

### Debug Excel Import
When importing Excel files, check browser console for:
```
File upload function called
Reading Excel file...
Excel data: [["User name","User ID","Phone number"],["john_doe","123456789","+1234567890"]]
Processing Excel row: {username: "john_doe", user_id: "123456789", phone: "+1234567890"}
Adding campaign user: {username: "john_doe", user_id: "123456789", phone: "+1234567890", priority: 1}
```

