# MIDA Certificate System - Frontend

A modern React-based frontend for the MIDA Certificate System, replacing the monolithic HTML file with a modular, maintainable architecture.

## 🚀 Tech Stack

- **React 18** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool & dev server
- **Tailwind CSS** - Utility-first styling
- **React Router** - Client-side routing
- **TanStack Query** - Server state management
- **Axios** - HTTP client
- **React Hot Toast** - Notifications
- **Lucide React** - Icons

## 📁 Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/                    # Reusable UI components
│   │   │   ├── Button.tsx
│   │   │   ├── Input.tsx
│   │   │   ├── Select.tsx
│   │   │   ├── Modal.tsx
│   │   │   ├── Table.tsx
│   │   │   ├── Card.tsx
│   │   │   ├── Badge.tsx
│   │   │   ├── Tabs.tsx
│   │   │   ├── Alert.tsx
│   │   │   ├── Breadcrumb.tsx
│   │   │   ├── FileUpload.tsx
│   │   │   └── index.ts
│   │   └── Layout.tsx             # Main layout with navigation
│   ├── pages/
│   │   ├── InvoiceConverter.tsx   # Invoice classification tab
│   │   ├── CertificateParser.tsx  # PDF parsing tab
│   │   ├── DatabaseView.tsx       # Certificates list view
│   │   ├── CertificateDetails.tsx # Single certificate view
│   │   ├── ItemImports.tsx        # Import records for an item
│   │   └── index.ts
│   ├── services/
│   │   ├── api.ts                 # Axios instance
│   │   ├── certificateService.ts  # Certificate CRUD
│   │   ├── classificationService.ts
│   │   ├── companyService.ts
│   │   ├── importService.ts
│   │   └── index.ts
│   ├── types/
│   │   └── index.ts               # TypeScript interfaces
│   ├── utils/
│   │   └── index.ts               # Utility functions
│   ├── App.tsx                    # Route definitions
│   ├── main.tsx                   # App entry point
│   └── index.css                  # Global styles
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tailwind.config.js
└── postcss.config.js
```

## 🛠️ Setup Instructions

### Prerequisites

- **Node.js 18+** - Download from https://nodejs.org/

### Installation

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```

4. Open http://localhost:3000 in your browser

### Backend Requirements

Make sure the FastAPI backend is running on `http://localhost:8000`. The Vite dev server proxies API requests to the backend.

## 📋 Features

### Invoice Converter
- Upload CSV/Excel invoice files
- Automatic classification into Form-D, MIDA, and Duties Payable
- Select items and export K1 declarations
- Real-time balance checking against certificates

### Certificate Parser
- Upload MIDA certificate PDFs
- OCR-powered data extraction via Azure Document Intelligence
- **Validation Warnings System**:
  - 🔴 **Errors (blocking)**: Missing required fields, duplicate line numbers
  - 🟡 **Warnings**: Missing optional fields, quantity discrepancies
  - 🔵 **Info**: Port allocation suggestions
- **Port Allocation Editing**: Edit Port Klang, KLIA, Bukit Kayu Hitam quantities
- **Quantity Discrepancy Detection**: Alerts when Approved Qty ≠ Sum of Station quantities
- Visual field highlighting for missing/problematic data
- Card view and table view for editing items
- Preview before saving to database

### Database View
- View all certificates with pagination
- Search by certificate number or company
- Soft delete and restore functionality
- View certificate items and their balances

### Certificate Details
- Full certificate information
- **Port Allocation Display**: Shows approved/remaining quantities per port
- List of items with quantity tracking
- Edit certificate details including port-wise quantities
- Navigate to import records

### Import Records
- Track imports against certificate items
- **Port Balance Breakdown**: Shows remaining balance per port
- Add new import declarations with port selection
- Edit and delete existing import records
- View quantity balance in real-time

## 🔧 Configuration

### Environment Variables

Create a `.env` file in the frontend directory:

```env
VITE_API_URL=http://localhost:8000
```

### API Proxy

The Vite dev server is configured to proxy `/api` requests to the backend:

```typescript
// vite.config.ts
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

## 🏗️ Build for Production

```bash
npm run build
```

The production build will be output to the `dist/` directory.

### Serve Production Build

```bash
npm run preview
```

## 📝 Development Notes

### Adding New Components

1. Create component in `src/components/ui/`
2. Export from `src/components/ui/index.ts`
3. Import using `import { ComponentName } from '@/components/ui'`

### Adding New Pages

1. Create page component in `src/pages/`
2. Export from `src/pages/index.ts`
3. Add route in `src/App.tsx`

### Adding New API Endpoints

1. Add method to appropriate service in `src/services/`
2. Use TanStack Query for data fetching in components

## 🔄 Migration from Old UI

This React frontend replaces the monolithic `web/index.html` file. All functionality has been preserved:

| Old Feature | New Location |
|-------------|--------------|
| Invoice Converter Tab | `/converter` route |
| Certificate Parser Tab | `/parser` route |
| Database View Tab | `/database` route |
| Certificate Modal | `/database/certificates/:id` page |
| Import Records Modal | `/database/certificates/:certId/items/:itemId/imports` page |

The API endpoints remain the same - only the frontend architecture has changed.
