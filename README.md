# Sign Estimation Application

A modern Python web application for sign manufacturing cost estimation and project management, built specifically for sign manufacturing companies with teams working on Windows machines with Microsoft 365.

## 🎯 Features

### Core Functionality

- **Project Management**: Create and manage sign installation projects
- **Building Organization**: Organize signs by buildings within projects
- **Sign Types**: Maintain master catalog of available sign types with pricing
- **Sign Groups**: Create reusable groups of signs for common configurations
- **Cost Calculation**: Multiple pricing methods:
  - Unit pricing per sign
  - Price per square foot based on material
  - Custom pricing overrides
- **Tree Visualization**: Visual project hierarchy showing projects → buildings → signs
- **Export Capabilities**: Generate estimates with company branding

### Pricing Methods

1. **Unit Price**: Fixed price per sign
2. **Material-Based**: Calculate cost based on material type and square footage
3. **Dimensional**: Custom sizing with price per square foot
4. **Installation & Tax**: Optional installation costs and sales tax calculation

### OneDrive Integration

- **Shared Database**: SQLite database optimized for OneDrive sharing
- **Automatic Deployment**: Scripts to deploy app to shared OneDrive folders
- **Team Collaboration**: Multiple users can access the same data
- **Conflict Resolution**: Database synchronization tools

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- Windows 10/11 (for production deployment)
- Microsoft 365 with OneDrive access
- Access to shared OneDrive folder

### Installation

1. **Clone/Download** the project to your development machine
2. **Setup Python Environment**:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Run the Application (macOS/Linux)**:
   ```bash
   # One-off
   .venv/bin/python app.py
   # Or using helper script (auto uses venv)
   SIGN_APP_INITIAL_CSV=Book2.csv SIGN_APP_PORT=8060 bash run_app.sh
   ```
4. **Run the Application (Windows)**:
   ```bat
   rem Direct
   .venv\Scripts\python.exe app.py
   rem Or batch launcher
   SET SIGN_APP_INITIAL_CSV=Book2.csv
   SET SIGN_APP_PORT=8060
   run_app.bat
   rem Or PowerShell
   $env:SIGN_APP_INITIAL_CSV="Book2.csv"; $env:SIGN_APP_PORT=8060; ./start_app.ps1
   ```
5. **Access the Application**:
   Open your web browser and go to `http://localhost:8050`

### Deployment to OneDrive

1. **Deploy to OneDrive** (path optional on Windows; script tries to autodetect):

   ```bash
   python scripts/deploy.py --onedrive-path "C:\\Users\\Username\\OneDrive\\Shared\\SignEstimation"
   # or attempt autodetect (Windows only)
   python scripts/deploy.py
   ```

2. **On Team Machines**: Navigate to the OneDrive folder and run `start_app.bat` or `start_app.ps1`

## 📊 Usage Guide

### Environment Variables

You can influence runtime behavior with:

- `SIGN_APP_DB` – alternate SQLite filename
- `SIGN_APP_INITIAL_CSV` – CSV auto-import (only if `sign_types` table empty)
- `SIGN_APP_PORT` – preferred port (auto-falls forward if busy)

### 1. Import Initial Data

- Go to the "Import Data" tab
- Upload your CSV file with sign types and pricing
- The system will automatically process and import the data

### 2. Create a Project

- Navigate to the "Projects" tab
- Click "Create Project"
- Enter project details including sales tax rate and installation settings

### 3. Add Buildings

- Select a project from the tree visualization
- Add buildings to organize your signs

### 4. Assign Signs

- **Individual Signs**: Add specific sign types with quantities to buildings
- **Sign Groups**: Create reusable sign packages and assign them to buildings

### 5. Generate Estimates

- Go to the "Estimates" tab
- Select your project
- Choose options for installation and sales tax
- Export to Excel with company branding

## 🏗️ Project Structure

```
Project_Pyramid_2/
├── app.py                 # Main Dash application
├── requirements.txt       # Python dependencies
├── assets/
│   └── LSI_Logo.svg      # Company logo
├── utils/
│   ├── database.py       # Database operations
│   ├── calculations.py   # Cost calculation logic
│   └── onedrive.py      # OneDrive integration
├── scripts/
│   ├── deploy.py        # Deployment script
│   └── sync_db.py       # Database sync script
└── README.md            # This file
```

## 💾 Database Schema

### Tables

- **projects**: Project information and settings
- **buildings**: Buildings within projects
- **sign_types**: Master catalog of available signs
- **sign_groups**: Reusable sign packages
- **sign_group_members**: Signs within each group
- **building_signs**: Individual signs assigned to buildings
- **building_sign_groups**: Sign groups assigned to buildings
- **material_pricing**: Material-based pricing rates

## 🔧 Configuration

### OneDrive Setup

The application creates configuration files automatically:

- `onedrive_config.json`: OneDrive path and sync settings
- `deployment_info.json`: Deployment status and history

### Database Optimization

The SQLite database is automatically optimized for OneDrive:

- WAL mode for better concurrent access
- Full synchronous mode for data integrity
- Optimized cache settings

## 🛠️ Development

### Adding New Features

1. **Database Changes**: Update `utils/database.py` with new table schemas
2. **Cost Calculations**: Extend `utils/calculations.py` for new pricing methods
3. **UI Components**: Add new tabs and components in `app.py`

### Testing

```bash
# Run the application in development mode
python app.py

# Test database functions
python -c "from utils.database import DatabaseManager; db = DatabaseManager(); print('Database OK')"

# Test OneDrive integration
python scripts/deploy.py --setup-only --onedrive-path "./test_onedrive"
```

## 📋 CSV Import Format

Your CSV should include the following columns (column names are flexible):

- **name**: Sign type name
- **description**: Sign description
- **price/unit_price**: Cost per sign
- **material**: Material type
- **width**: Sign width (for area calculations)
- **height**: Sign height (for area calculations)

Example CSV:

```csv
name,description,price,material,width,height
"ADA Room Sign","Standard ADA compliant room identification",45.00,"Brushed Aluminum",8,2
"Wayfinding Arrow","Directional wayfinding signage",65.00,"Acrylic",12,4
"Building Directory","Multi-tenant directory board",350.00,"Aluminum Frame",36,48
```

## 🤝 Team Collaboration

### For Administrators

1. Set up the OneDrive shared folder
2. Deploy the application using the deployment script
3. Share the OneDrive folder with team members
4. Provide training on the application interface

### For Team Members

1. Access the shared OneDrive folder
2. Run the startup script (`start_app.bat`)
3. Use the web interface to create estimates
4. Database changes sync automatically through OneDrive

## 🔒 Data Security & Backup

- **Automatic Backups**: Database changes are synced to OneDrive
- **Version Control**: OneDrive maintains file version history
- **Access Control**: Managed through OneDrive sharing permissions
- **Data Integrity**: SQLite ACID compliance ensures data consistency

## 📞 Support

For technical issues:

1. Check the deployment logs in the OneDrive folder
2. Verify Python installation and dependencies
3. Ensure OneDrive sync is working properly
4. Contact your IT administrator for OneDrive access issues

## 📄 License

This application is proprietary software developed for internal use by the sign manufacturing company.

---

**Last Updated**: September 2025  
**Version**: 1.0.0  
**Compatibility**: Windows 10/11, Python 3.8+, Microsoft 365
