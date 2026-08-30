"""Mock data for Skylark Drones BI Agent - enables demo without API credentials"""

MOCK_DEALS = {
    "data": {
        "boards": [
            {
                "id": "1234567890",
                "name": "Sales Pipeline",
                "items": [
                    {"id": "1", "name": "Acme Corp Deal", "column_values": [
                        {"id": "status", "text": "Negotiation"},
                        {"id": "amount", "text": "5000"},
                        {"id": "contact_email", "text": "john@acme.com"}
                    ]},
                    {"id": "2", "name": "TechStart Inc Deal", "column_values": [
                        {"id": "status", "text": "Proposal"},
                        {"id": "amount", "text": "7500"},
                        {"id": "contact_email", "text": ""}
                    ]},
                    {"id": "3", "name": "Global Solutions Deal", "column_values": [
                        {"id": "status", "text": "Won"},
                        {"id": "amount", "text": "10000"},
                        {"id": "contact_email", "text": "sarah@global.com"}
                    ]},
                    {"id": "4", "name": "Enterprise Ltd Deal", "column_values": [
                        {"id": "status", "text": "Negotiation"},
                        {"id": "amount", "text": "15000"},
                        {"id": "contact_email", "text": ""}
                    ]},
                    {"id": "5", "name": "Innovation Hub Deal", "column_values": [
                        {"id": "status", "text": "Lost"},
                        {"id": "amount", "text": "3500"},
                        {"id": "contact_email", "text": ""}
                    ]},
                ]
            }
        ]
    }
}

MOCK_WORK_ORDERS = {
    "data": {
        "boards": [
            {
                "id": "0987654321",
                "name": "Work Orders",
                "items": [
                    {"id": "wo1", "name": "WO-2024-001", "column_values": [
                        {"id": "status", "text": "Done"},
                        {"id": "priority", "text": "High"},
                        {"id": "assigned_to", "text": "Alpha Team"}
                    ]},
                    {"id": "wo2", "name": "WO-2024-002", "column_values": [
                        {"id": "status", "text": "In Progress"},
                        {"id": "priority", "text": "High"},
                        {"id": "assigned_to", "text": "Beta Team"}
                    ]},
                    {"id": "wo3", "name": "WO-2024-003", "column_values": [
                        {"id": "status", "text": "In Progress"},
                        {"id": "priority", "text": "Medium"},
                        {"id": "assigned_to", "text": "Gamma Team"}
                    ]},
                    {"id": "wo4", "name": "WO-2024-004", "column_values": [
                        {"id": "status", "text": "Not Started"},
                        {"id": "priority", "text": "Medium"},
                        {"id": "assigned_to", "text": "Delta Team"}
                    ]},
                ]
            }
        ]
    }
}

def get_mock_board_data(board_id):
    """Get mock data for a specific board"""
    if board_id == "1234567890":
        return MOCK_DEALS
    elif board_id == "0987654321":
        return MOCK_WORK_ORDERS
    else:
        # Generic mock response
        return {
            "data": {
                "boards": [
                    {
                        "id": board_id,
                        "name": f"Board {board_id}",
                        "items": []
                    }
                ]
            }
        }

def get_mock_stats():
    """Return summary statistics for leadership/analytics"""
    return {
        "total_deals": 346,
        "active_work_orders": 177,
        "pipeline_value": 1200000,
        "completion_rate": 87,
        "closed_this_month": 8,
        "completed_work_orders": 24,
        "quality_issues_resolved": 342,
        "revenue_generated": 45000,
        "deals_by_status": {
            "Negotiation": 89,
            "Proposal": 124,
            "Won": 89,
            "Lost": 44
        },
        "deals_by_value": {
            "0-5K": 156,
            "5-10K": 124,
            "10-25K": 54,
            "25K+": 12
        }
    }
