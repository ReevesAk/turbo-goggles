# Event/Ticketing Feature Documentation

## Overview

The Event/Ticketing system is a comprehensive solution for creating, managing, and selling event tickets. It supports a complete lifecycle from event creation to attendee check-in, with features including QR code generation, ticket transfers, cart-based purchasing, and payment processing.

## Table of Contents

- [High-Level Architecture](#high-level-architecture)
- [System Components](#system-components)
- [User Roles](#user-roles)
- [Core Features](#core-features)
- [Data Models](#data-models)

---

## High-Level Architecture

```mermaid
graph TB
    subgraph "Frontend"
        MobileApp[Mobile App]
        WebApp[Web App]
        AdminPanel[Admin Panel]
        PartnerApp[Partner App]
    end

    subgraph "API Layer"
        REST[REST API Gateway]
        Auth[Authentication]
        RateLimit[Rate Limiting]
    end

    subgraph "Business Logic"
        EventMgmt[Event Management]
        TicketMgmt[Ticket Management]
        CartMgmt[Cart Management]
        PaymentMgmt[Payment Processing]
        QRService[QR Code Service]
        TransferMgmt[Transfer Management]
        CheckInMgmt[Check-in Service]
    end

    subgraph "Data Layer"
        DB[(PostgreSQL)]
        Cache[(Redis Cache)]
        Media[(Cloudinary)]
    end

    subgraph "External Services"
        Paystack[Paystack Payment]
        Wallet[Wallet Service]
        Email[Email Service]
    end

    MobileApp --> REST
    WebApp --> REST
    AdminPanel --> REST
    PartnerApp --> REST

    REST --> Auth
    REST --> RateLimit

    Auth --> EventMgmt
    Auth --> TicketMgmt
    Auth --> CartMgmt

    EventMgmt --> DB
    EventMgmt --> Cache

    TicketMgmt --> DB
    TicketMgmt --> QRService

    CartMgmt --> DB
    CartMgmt --> PaymentMgmt

    QRService --> Media
    QRService --> Email

    PaymentMgmt --> Paystack
    PaymentMgmt --> Wallet

    TransferMgmt --> DB
    TransferMgmt --> Email

    CheckInMgmt --> DB
    CheckInMgmt --> Cache
```

---

## System Components

### 1. Event Management

- Create and manage events
- Event approval workflow (Draft → In Review → On Sale)
- Event categorization and tagging
- View count tracking

### 2. Ticket Management

- Multiple ticket types per event
- Configurable pricing and capacity
- Unlimited slots option
- Sales start/end dates
- Slot capacity management
- Minimum/maximum purchase limits per ticket type

### 3. Cart Management

- **Multi-ticket checkout**: Purchase multiple ticket types in a single transaction
- **Same-event validation**: All cart items must belong to the same event
- **Atomic order processing**: All line items processed in a single database transaction
- **Combined payment**: Single payment for all cart items
- **Order history**: Track all past orders with their line items
- **Idempotency support**: Prevent duplicate orders with idempotency keys

### 4. QR Code System

- QR code generation using `qrcode` library
- Cloudinary upload for QR images
- Token-based verification
- Human-readable fallback codes
- Follows StoreVisitQRCode pattern

### 5. Payment Processing

- **Wallet Payment**: Debits from user's 9PSB wallet
- **Card Payment**: Paystack transaction verification

### 6. Ticket Transfers

- Time-limited transfer windows
- Invite-based transfer system
- Accept/Decline workflow
- Automatic cancellation of pending transfers

### 7. Check-in System

- QR code scanning
- Manual fallback code entry
- Check-in tracking with timestamps
- Audit logging

---

## User Roles

### Role Descriptions

| Role           | Description                 | Key Responsibilities                                                                          |
| -------------- | --------------------------- | --------------------------------------------------------------------------------------------- |
| **Member**     | End users who attend events | Browse events, purchase tickets (single or cart), view owned tickets, transfer tickets        |
| **Partner**    | Event organizers/owners     | Create and manage events, create ticket types, **perform door check-ins**, view sales ledger  |
| **Admin**      | System administrators       | Review and approve events, grant sale windows, configure system settings, oversee settlements |
| **SuperAdmin** | Full system access          | All admin capabilities plus system-wide oversight                                             |

```mermaid
graph LR
    subgraph "Roles"
        Member[Member]
        Partner[Partner]
        Admin[Admin]
        SuperAdmin[SuperAdmin]
    end

    subgraph "Member Permissions"
        M1[Browse Events]
        M2[Purchase Tickets]
        M3[Cart Checkout]
        M4[View Tickets]
        M5[Transfer Tickets]
        M6[View Orders]
    end

    subgraph "Partner Permissions"
        P1[Create Events]
        P2[Manage Tickets]
        P3[View Sales]
        P4[Check-in Tickets]
        P5[View Check-in Stats]
    end

    subgraph "Admin Permissions"
        A1[Review Events]
        A2[Grant Sale Windows]
        A3[Configure System]
        A4[Refund Purchases]
        A5[View Statistics]
    end

    Member --> M1
    Member --> M2
    Member --> M3
    Member --> M4
    Member --> M5
    Member --> M6

    Partner --> P1
    Partner --> P2
    Partner --> P3
    Partner --> P4
    Partner --> P5

    Admin --> A1
    Admin --> A2
    Admin --> A3
    Admin --> A4
    Admin --> A5

    SuperAdmin --> Admin
```

---

## Core Features

### Event Lifecycle

```mermaid
stateDiagram-v2
    [*] --> DRAFT: Partner Creates
    DRAFT --> IN_REVIEW: Partner Submits
    IN_REVIEW --> ON_SALE: Admin Approves
    IN_REVIEW --> REJECTED: Admin Rejects
    REJECTED --> DRAFT: Partner Edits & Resubmits
    ON_SALE --> EXPIRED: End Date Passes
    ON_SALE --> CANCELLED: Admin Cancels
    ON_SALE --> [*]: All Slots Filled
    EXPIRED --> [*]
    CANCELLED --> [*]
    REJECTED --> [*]
```

### Single Ticket Purchase Flow

```mermaid
sequenceDiagram
    actor Member
    participant API
    participant TicketMgmt
    participant Payment
    participant QRService
    participant DB

    Member->>API: Select Ticket & Quantity
    API->>TicketMgmt: Validate Availability
    TicketMgmt->>DB: Check Slot Capacity
    DB-->>TicketMgmt: Slots Available
    TicketMgmt-->>API: Valid

    Member->>API: Choose Payment Method
    alt Wallet Payment
        API->>Payment: verify_wallet_auth()
        Payment-->>API: Verified
        API->>Payment: Wallet.Debit()
        Payment-->>API: Success
    else Card Payment
        API->>Payment: Paystack.verify_transaction()
        Payment-->>API: Success
    end

    API->>DB: Create TicketPurchase (PAID)
    DB-->>API: Purchase Created

    API->>TicketMgmt: Issue Tickets
    TicketMgmt->>DB: Create TicketCode(s)

    API->>QRService: Generate QR Codes
    QRService->>QRService: Create QR Image
    QRService->>Cloudinary: Upload
    Cloudinary-->>QRService: URL
    QRService-->>API: QR Data

    API->>DB: Save QR Image URL
    API->>DB: Create PartnerTicketSale
    API->>DB: Create TxModel Record

    API-->>Member: Tickets with QR Codes
```

### Cart Checkout Flow (Multiple Ticket Types)

```mermaid
sequenceDiagram
    actor Member
    participant API
    participant CartMgmt
    participant TicketMgmt
    participant Payment
    participant QRService
    participant DB

    Member->>API: Add Items to Cart
    Note over Member,API: Ticket A x5, Ticket B x3, Ticket C x10

    API->>CartMgmt: Validate Cart Items
    CartMgmt->>TicketMgmt: Validate Each Ticket
    TicketMgmt->>DB: Check Slot Capacity (All Tickets)
    DB-->>TicketMgmt: All Slots Available

    CartMgmt->>CartMgmt: Validate Same Event
    CartMgmt->>CartMgmt: Calculate Total Amount
    CartMgmt-->>API: Cart Valid - Total: ₦XXX

    Member->>API: Checkout with Payment Method
    alt Wallet Payment
        API->>Payment: verify_wallet_auth()
        Payment-->>API: Verified
        API->>Payment: Wallet.Debit(total)
        Payment-->>API: Success
    else Card Payment
        API->>Payment: Paystack.verify_transaction()
        Payment-->>API: Success
    end

    API->>DB: Create TicketOrder (PAID)
    API->>DB: Create TicketPurchase Line Items
    Note over DB: Line Item 1: Ticket A x5<br/>Line Item 2: Ticket B x3<br/>Line Item 3: Ticket C x10

    API->>TicketMgmt: Reserve Slots for All Tickets
    TicketMgmt->>DB: Atomic Slot Update

    API->>TicketMgmt: Issue All Ticket Codes
    TicketMgmt->>DB: Bulk Create 18 TicketCodes

    API->>QRService: Generate QR Codes (18 codes)
    QRService->>Cloudinary: Upload All QR Images
    Cloudinary-->>QRService: URLs
    QRService-->>API: QR Data

    API->>DB: Create PartnerTicketSale Records (3)
    API->>DB: Create TxModel Record (1)

    API-->>Member: All Tickets with QR Codes
```

### Transfer Flow

```mermaid
sequenceDiagram
    actor Sender as Member (Sender)
    actor Recipient as Member (Recipient)
    participant API
    participant Transfer
    participant Notification
    participant DB

    Sender->>API: Request Transfer
    API->>Transfer: Validate Ticket Ownership
    Transfer->>DB: Check Transfer Window
    DB-->>Transfer: Within Window
    Transfer->>DB: Check Not Checked In
    DB-->>Transfer: Not Checked In

    API->>DB: Create TicketTransfer (PENDING)
    API->>Notification: Notify Recipient

    Recipient->>API: View Pending Transfers
    API->>DB: Fetch Transfers
    DB-->>API: Transfer List

    alt Accept
        Recipient->>API: Accept Transfer
        API->>Transfer: Validate & Execute
        Transfer->>DB: Update TicketCode Owner
        Transfer->>DB: Cancel Other Pending
        Transfer->>DB: Update Transfer Status
        API->>Notification: Notify Both Parties
    else Decline
        Recipient->>API: Decline Transfer
        Transfer->>DB: Update Transfer Status
        API->>Notification: Notify Sender
    else Cancel
        Sender->>API: Cancel Transfer
        Transfer->>DB: Update Transfer Status
        API->>Notification: Notify Recipient
    end
```

### Check-in Flow (Performed by Partner)

```mermaid
sequenceDiagram
    actor Attendee
    actor PartnerStaff
    participant App
    participant API
    participant QRService
    participant DB

    Attendee->>App: Show QR Code
    PartnerStaff->>App: Scan QR Code

    alt QR Scan
        App->>API: Verify QR (token)
        API->>QRService: TicketCode.verify(token)
        QRService->>DB: Query by token
    else Manual Entry
        App->>API: Verify (code)
        API->>QRService: TicketCode.verify(code)
        QRService->>DB: Query by code
    end

    DB-->>QRService: TicketCode Found
    QRService->>QRService: Validate Event Ownership
    QRService->>QRService: Check Not Checked In
    QRService-->>API: Valid Ticket

    API->>DB: Update Check-in Status
    API->>DB: Record Checked In At
    API->>DB: Record Checked In By (Partner)
    API->>Notification: Notify Attendee

    API-->>App: Check-in Success
    App-->>PartnerStaff: Confirmation
    App-->>Attendee: Success Notification
```

---

## Data Models

```mermaid
erDiagram
    Event ||--o{ Ticket : contains
    Event ||--o{ TicketOrder : has
    Event ||--o{ TicketPurchase : has
    Event ||--o{ PartnerSaleWindow : has
    Event ||--o{ PartnerTicketSale : generates

    Ticket ||--o{ TicketPurchase : purchased_as
    Ticket ||--o{ PartnerTicketSale : sold_as

    TicketOrder ||--o{ TicketPurchase : contains
    TicketPurchase ||--o{ TicketCode : issues
    TicketPurchase ||--|| PartnerTicketSale : maps_to

    TicketCode ||--o{ TicketTransfer : transfer_request

    User ||--o{ Event : owns
    User ||--o{ TicketOrder : places
    User ||--o{ TicketPurchase : makes
    User ||--o{ TicketCode : owns
    User ||--o{ TicketTransfer : initiates
    User ||--o{ TicketCode : checks_in
    User ||--o{ PartnerSaleWindow : granted_to

    TicketConfiguration ||--|| "Singleton" : config

    Event {
        UUID id PK
        UUID user_id FK
        string business_name
        string event_name
        string slug
        text description
        string status
        datetime start_date
        datetime end_date
        json media
        int view_count
        text address
    }

    Ticket {
        UUID id PK
        UUID event_id FK
        string name
        decimal price
        int slot_cap
        int slots_filled
        bool unlimited_slots
        datetime sales_start_date
        datetime sales_end_date
        int min_purchase
        int max_purchase
    }

    TicketOrder {
        UUID id PK
        UUID member_id FK
        UUID event_id FK
        string status
        decimal total_amount
        string payment_reference
        string idempotency_key
        datetime created_at
        datetime expires_at
    }

    TicketPurchase {
        UUID id PK
        UUID order_id FK
        UUID member_id FK
        UUID ticket_id FK
        UUID event_id FK
        int quantity
        decimal unit_price
        decimal total_amount
        string status
        datetime purchased_at
    }

    TicketCode {
        UUID id PK
        UUID purchase_id FK
        UUID current_owner_id FK
        UUID token
        string code
        string qr_image_url
        bool is_checked_in
        datetime checked_in_at
        UUID checked_in_by FK
        datetime created_at
    }

    TicketTransfer {
        UUID id PK
        UUID ticket_code_id FK
        UUID from_user_id FK
        UUID to_user_id FK
        string status
        datetime requested_at
        datetime responded_at
        datetime invite_expires_at
    }

    PartnerTicketSale {
        UUID id PK
        UUID partner_id FK
        UUID event_id FK
        UUID ticket_id FK
        UUID purchase_id FK
        decimal gross_amount
        decimal platform_fee_percentage
        decimal platform_fee_amount
        decimal net_amount
        string settlement_status
        datetime settled_at
        string payout_reference
        int settlement_attempts
    }
```

---

### Payment Security

- **Wallet Authentication**: PIN or biometric verification required for wallet payments
- **Payment Verification**: External payment references are verified before ticket issuance
- **Amount Validation**: Card payments validate amount in kobo (smallest currency unit)
- **Single Payment**: Cart checkout processes one payment for all items, reducing transaction fees

---

## License

Copyright © 2024 Picadailys. All rights reserved.
