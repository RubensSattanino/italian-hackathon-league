"""Default HubSpot-like schema: object types, default properties, pipelines, association types."""

OBJECT_TYPES = {
    "contacts": "0-1", "companies": "0-2", "deals": "0-3", "tickets": "0-5",
    "products": "0-7", "line_items": "0-8", "quotes": "0-14", "notes": "0-46",
    "calls": "0-48", "emails": "0-49", "meetings": "0-47", "tasks": "0-27",
}
TYPE_BY_ID = {v: k for k, v in OBJECT_TYPES.items()}
SINGULAR = {
    "contact": "contacts", "company": "companies", "deal": "deals", "ticket": "tickets",
    "product": "products", "line_item": "line_items", "lineitem": "line_items", "line_items": "line_items",
    "quote": "quotes", "note": "notes", "call": "calls", "email": "emails", "meeting": "meetings",
    "task": "tasks",
}
SINGULAR_OF = {
    "contacts": "contact", "companies": "company", "deals": "deal", "tickets": "ticket",
    "products": "product", "line_items": "line_item", "quotes": "quote", "notes": "note",
    "calls": "call", "emails": "email", "meetings": "meeting", "tasks": "task",
}


def norm_type(t):
    if t is None:
        return None
    t = str(t).strip().lower()
    if t in OBJECT_TYPES:
        return t
    if t in SINGULAR:
        return SINGULAR[t]
    if t in TYPE_BY_ID:
        return TYPE_BY_ID[t]
    if t.endswith("s") and t[:-1] in SINGULAR:
        return SINGULAR[t[:-1]]
    return None


def _p(name, label, type_="string", field="text", group="information", options=None, **kw):
    d = {"name": name, "label": label, "type": type_, "fieldType": field, "groupName": group,
         "description": "", "options": options or [], "hasUniqueValue": False, "hidden": False,
         "formField": False, "calculated": False, "externalOptions": False,
         "displayOrder": -1}
    d.update(kw)
    return d


def _opts(pairs):
    return [{"label": l, "value": v, "displayOrder": i, "hidden": False} for i, (v, l) in enumerate(pairs)]


COMMON = [
    _p("hs_object_id", "Record ID", "number", "number", modificationMetadata={"readOnlyValue": True}),
    _p("createdate", "Create Date", "datetime", "date"),
    _p("hs_lastmodifieddate", "Last Modified Date", "datetime", "date"),
    _p("hubspot_owner_id", "Owner", "enumeration", "select"),
]

LIFECYCLE = _opts([("subscriber", "Subscriber"), ("lead", "Lead"), ("marketingqualifiedlead", "Marketing Qualified Lead"),
                   ("salesqualifiedlead", "Sales Qualified Lead"), ("opportunity", "Opportunity"),
                   ("customer", "Customer"), ("evangelist", "Evangelist"), ("other", "Other")])
PRIORITY = _opts([("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High"), ("URGENT", "Urgent")])
TASK_STATUS = _opts([("NOT_STARTED", "Not started"), ("IN_PROGRESS", "In progress"), ("WAITING", "Waiting"),
                     ("COMPLETED", "Completed"), ("DEFERRED", "Deferred")])
CURRENCY = _opts([("EUR", "EUR"), ("USD", "USD"), ("GBP", "GBP")])

DEFAULT_PROPERTIES = {
    "contacts": [
        _p("email", "Email", group="contactinformation"), _p("firstname", "First Name", group="contactinformation"),
        _p("lastname", "Last Name", group="contactinformation"), _p("phone", "Phone Number", field="phonenumber", group="contactinformation"),
        _p("mobilephone", "Mobile Phone Number", field="phonenumber", group="contactinformation"),
        _p("company", "Company Name", group="contactinformation"), _p("website", "Website URL", group="contactinformation"),
        _p("jobtitle", "Job Title", group="contactinformation"), _p("city", "City", group="contactinformation"),
        _p("state", "State/Region", group="contactinformation"), _p("country", "Country/Region", group="contactinformation"),
        _p("address", "Street Address", group="contactinformation"), _p("zip", "Postal Code", group="contactinformation"),
        _p("lifecyclestage", "Lifecycle Stage", "enumeration", "radio", group="contactinformation", options=LIFECYCLE),
        _p("hs_lead_status", "Lead Status", "enumeration", "radio", group="contactinformation"),
        _p("associatedcompanyid", "Primary Associated Company ID", "number", "number", group="contactinformation"),
        _p("lastmodifieddate", "Last Modified Date", "datetime", "date"),
        _p("hs_additional_emails", "Additional email addresses", "enumeration", "checkbox"),
    ],
    "companies": [
        _p("name", "Company name", group="companyinformation"), _p("domain", "Company Domain Name", group="companyinformation"),
        _p("hs_additional_domains", "Additional Domains", "enumeration", "checkbox", group="companyinformation"),
        _p("website", "Website URL", group="companyinformation"),
        _p("city", "City", group="companyinformation"), _p("state", "State/Region", group="companyinformation"),
        _p("country", "Country/Region", group="companyinformation"), _p("address", "Street Address", group="companyinformation"),
        _p("zip", "Postal Code", group="companyinformation"), _p("phone", "Phone Number", field="phonenumber", group="companyinformation"),
        _p("industry", "Industry", "enumeration", "select", group="companyinformation"),
        _p("description", "Description", field="textarea", group="companyinformation"),
        _p("numberofemployees", "Number of Employees", "number", "number", group="companyinformation"),
        _p("annualrevenue", "Annual Revenue", "number", "number", group="companyinformation"),
        _p("lifecyclestage", "Lifecycle Stage", "enumeration", "radio", group="companyinformation", options=LIFECYCLE),
        _p("type", "Type", "enumeration", "select", group="companyinformation"),
    ],
    "deals": [
        _p("dealname", "Deal Name", group="dealinformation"), _p("amount", "Amount", "number", "number", group="dealinformation"),
        _p("dealstage", "Deal Stage", "enumeration", "radio", group="dealinformation"),
        _p("pipeline", "Pipeline", "enumeration", "select", group="dealinformation"),
        _p("closedate", "Close Date", "datetime", "date", group="dealinformation"),
        _p("deal_currency_code", "Currency", "enumeration", "select", group="dealinformation", options=CURRENCY),
        _p("dealtype", "Deal Type", "enumeration", "radio", group="dealinformation",
           options=_opts([("newbusiness", "New Business"), ("existingbusiness", "Existing Business")])),
        _p("description", "Deal Description", field="textarea", group="dealinformation"),
        _p("hs_priority", "Priority", "enumeration", "select", group="dealinformation"),
        _p("hs_is_closed", "Is Closed", "bool", "booleancheckbox", group="dealinformation"),
        _p("hs_is_closed_won", "Is Closed Won", "bool", "booleancheckbox", group="dealinformation"),
    ],
    "tickets": [
        _p("subject", "Ticket name", group="ticketinformation"), _p("content", "Ticket description", field="textarea", group="ticketinformation"),
        _p("hs_pipeline", "Pipeline", "enumeration", "select", group="ticketinformation"),
        _p("hs_pipeline_stage", "Ticket status", "enumeration", "radio", group="ticketinformation"),
        _p("hs_ticket_priority", "Priority", "enumeration", "select", group="ticketinformation", options=PRIORITY),
        _p("hs_ticket_category", "Category", "enumeration", "checkbox", group="ticketinformation"),
        _p("closed_date", "Close date", "datetime", "date", group="ticketinformation"),
        _p("source_type", "Source", "enumeration", "select", group="ticketinformation"),
    ],
    "products": [
        _p("name", "Name", group="productinformation"), _p("description", "Description", field="textarea", group="productinformation"),
        _p("price", "Unit price", "number", "number", group="productinformation"), _p("hs_sku", "SKU", group="productinformation"),
        _p("hs_cost_of_goods_sold", "Unit cost", "number", "number", group="productinformation"),
        _p("hs_recurring_billing_period", "Term", group="productinformation"),
        _p("recurringbillingfrequency", "Billing frequency", "enumeration", "select", group="productinformation"),
    ],
    "line_items": [
        _p("name", "Name", group="lineiteminformation"), _p("description", "Description", field="textarea", group="lineiteminformation"),
        _p("quantity", "Quantity", "number", "number", group="lineiteminformation"),
        _p("price", "Unit price", "number", "number", group="lineiteminformation"),
        _p("amount", "Net price", "number", "number", group="lineiteminformation"),
        _p("hs_product_id", "Product ID", "number", "number", group="lineiteminformation"),
        _p("hs_sku", "SKU", group="lineiteminformation"),
        _p("hs_discount_percentage", "Discount percentage", "number", "number", group="lineiteminformation"),
        _p("discount", "Unit discount", "number", "number", group="lineiteminformation"),
        _p("hs_line_item_currency_code", "Currency", "enumeration", "select", group="lineiteminformation", options=CURRENCY),
    ],
    "quotes": [
        _p("hs_title", "Quote name", group="quoteinformation"), _p("hs_expiration_date", "Expiration date", "datetime", "date", group="quoteinformation"),
        _p("hs_status", "Quote approval status", "enumeration", "select", group="quoteinformation"),
        _p("hs_currency", "Currency", "enumeration", "select", group="quoteinformation", options=CURRENCY),
        _p("hs_language", "Language", "enumeration", "select", group="quoteinformation"),
        _p("hs_quote_amount", "Amount", "number", "number", group="quoteinformation"),
    ],
    "notes": [
        _p("hs_note_body", "Note body", field="html", group="engagement"), _p("hs_timestamp", "Activity date", "datetime", "date", group="engagement"),
        _p("hs_attachment_ids", "Attachment IDs", group="engagement"),
    ],
    "calls": [
        _p("hs_call_body", "Call notes", field="html", group="engagement"), _p("hs_call_title", "Call Title", group="engagement"),
        _p("hs_timestamp", "Activity date", "datetime", "date", group="engagement"),
        _p("hs_call_direction", "Call direction", "enumeration", "select", group="engagement",
           options=_opts([("INBOUND", "Inbound"), ("OUTBOUND", "Outbound")])),
        _p("hs_call_duration", "Call duration", "number", "number", group="engagement"),
        _p("hs_call_status", "Call status", "enumeration", "select", group="engagement"),
        _p("hs_call_disposition", "Call outcome", "enumeration", "select", group="engagement"),
        _p("hs_call_from_number", "From number", group="engagement"), _p("hs_call_to_number", "To number", group="engagement"),
    ],
    "emails": [
        _p("hs_email_text", "Email body", field="textarea", group="engagement"), _p("hs_email_html", "Email HTML", field="html", group="engagement"),
        _p("hs_email_subject", "Email subject", group="engagement"), _p("hs_timestamp", "Activity date", "datetime", "date", group="engagement"),
        _p("hs_email_direction", "Email direction", "enumeration", "select", group="engagement",
           options=_opts([("EMAIL", "Outgoing"), ("INCOMING_EMAIL", "Incoming"), ("FORWARDED_EMAIL", "Forwarded")])),
        _p("hs_email_status", "Email send status", "enumeration", "select", group="engagement"),
        _p("hs_email_headers", "Email headers", group="engagement"),
    ],
    "meetings": [
        _p("hs_meeting_title", "Meeting name", group="engagement"), _p("hs_meeting_body", "Meeting description", field="html", group="engagement"),
        _p("hs_timestamp", "Activity date", "datetime", "date", group="engagement"),
        _p("hs_meeting_start_time", "Start time", "datetime", "date", group="engagement"),
        _p("hs_meeting_end_time", "End time", "datetime", "date", group="engagement"),
        _p("hs_meeting_location", "Location", group="engagement"),
        _p("hs_meeting_outcome", "Meeting outcome", "enumeration", "select", group="engagement"),
        _p("hs_internal_meeting_notes", "Internal notes", field="html", group="engagement"),
    ],
    "tasks": [
        _p("hs_task_subject", "Task title", group="engagement"), _p("hs_task_body", "Task notes", field="html", group="engagement"),
        _p("hs_timestamp", "Due date", "datetime", "date", group="engagement"),
        _p("hs_task_status", "Task status", "enumeration", "select", group="engagement", options=TASK_STATUS),
        _p("hs_task_priority", "Priority", "enumeration", "select", group="engagement",
           options=_opts([("NONE", "None"), ("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")])),
        _p("hs_task_type", "Task type", "enumeration", "select", group="engagement",
           options=_opts([("TODO", "To-do"), ("CALL", "Call"), ("EMAIL", "Email")])),
        _p("hs_task_completion_date", "Completed at", "datetime", "date", group="engagement"),
    ],
}

GROUPS = {
    "contacts": [("contactinformation", "Contact information")],
    "companies": [("companyinformation", "Company information")],
    "deals": [("dealinformation", "Deal information")],
    "tickets": [("ticketinformation", "Ticket information")],
    "products": [("productinformation", "Product information")],
    "line_items": [("lineiteminformation", "Line item information")],
    "quotes": [("quoteinformation", "Quote information")],
    "notes": [("engagement", "Engagement")], "calls": [("engagement", "Engagement")],
    "emails": [("engagement", "Engagement")], "meetings": [("engagement", "Engagement")],
    "tasks": [("engagement", "Engagement")],
}
for _t in GROUPS:
    GROUPS[_t] = GROUPS[_t] + [("information", "Information")]


def default_properties(t):
    return [dict(p) for p in COMMON] + [dict(p) for p in DEFAULT_PROPERTIES.get(t, [])]


def _stage(id_, label, order, prob, closed):
    return {"id": id_, "label": label, "displayOrder": order,
            "metadata": {"isClosed": "true" if closed else "false", "probability": str(prob)}}


def default_pipelines():
    deal = {"id": "default", "label": "Sales Pipeline", "displayOrder": 0, "stages": [
        _stage("appointmentscheduled", "Appointment Scheduled", 0, 0.2, False),
        _stage("qualifiedtobuy", "Qualified To Buy", 1, 0.4, False),
        _stage("presentationscheduled", "Presentation Scheduled", 2, 0.6, False),
        _stage("decisionmakerboughtin", "Decision Maker Bought-In", 3, 0.8, False),
        _stage("contractsent", "Contract Sent", 4, 0.9, False),
        _stage("closedwon", "Closed Won", 5, 1.0, True),
        _stage("closedlost", "Closed Lost", 6, 0.0, True),
    ]}
    tick = {"id": "0", "label": "Support Pipeline", "displayOrder": 0, "stages": [
        {"id": "1", "label": "New", "displayOrder": 0, "metadata": {"ticketState": "OPEN", "isClosed": "false"}},
        {"id": "2", "label": "Waiting on contact", "displayOrder": 1, "metadata": {"ticketState": "OPEN", "isClosed": "false"}},
        {"id": "3", "label": "Waiting on us", "displayOrder": 2, "metadata": {"ticketState": "OPEN", "isClosed": "false"}},
        {"id": "4", "label": "Closed", "displayOrder": 3, "metadata": {"ticketState": "CLOSED", "isClosed": "true"}},
    ]}
    return {"deals": [deal], "tickets": [tick]}


# HUBSPOT_DEFINED association type ids: (from, to) -> [(typeId, label)] ; first is default
ASSOC = {}


def _a(f, t, default_id, primary_id=None, rev_default=None, rev_primary=None):
    ASSOC[(f, t)] = [(default_id, None)] + ([(primary_id, "Primary")] if primary_id else [])
    if rev_default:
        ASSOC[(t, f)] = [(rev_default, None)] + ([(rev_primary, "Primary")] if rev_primary else [])


_a("contacts", "companies", 279, 1, 280, 2)
_a("deals", "contacts", 3, None, 4)
_a("deals", "companies", 341, 5, 342, 6)
_a("tickets", "contacts", 16, None, 15)
_a("tickets", "companies", 339, 26, 340, 25)
_a("tickets", "deals", 28, None, 27)
_a("line_items", "deals", 20, None, 19)
_a("quotes", "deals", 64, None, 63)
_a("quotes", "line_items", 67, None, 68)
_a("quotes", "contacts", 69, None, 70)
_a("quotes", "companies", 71, None, 72)
_a("contacts", "contacts", 449, None, 449)
_a("companies", "companies", 450, None, 450)
_a("deals", "deals", 451, None, 451)
_a("products", "line_items", 0)  # placeholder unused
ASSOC.pop(("products", "line_items"), None)
for _eng, ids in {
    "notes": (202, 201, 190, 189, 214, 213, 228, 227),
    "calls": (194, 193, 182, 181, 206, 205, 220, 219),
    "emails": (198, 197, 186, 185, 210, 209, 224, 223),
    "meetings": (200, 199, 188, 187, 212, 211, 226, 225),
    "tasks": (204, 203, 192, 191, 216, 215, 230, 229),
}.items():
    _a(_eng, "contacts", ids[0], None, ids[1])
    _a(_eng, "companies", ids[2], None, ids[3])
    _a(_eng, "deals", ids[4], None, ids[5])
    _a(_eng, "tickets", ids[6], None, ids[7])

TYPE_ID_INFO = {}  # typeId -> (from, to, label)
for (f, t), lst in ASSOC.items():
    for tid, label in lst:
        TYPE_ID_INFO.setdefault(tid, (f, t, label))


def default_assoc_type(f, t):
    lst = ASSOC.get((f, t))
    if lst:
        return lst[0][0]
    return None


def reverse_type_id(f, t, type_id):
    """Given from->to typeId, return the to->from typeId."""
    fwd = ASSOC.get((f, t), [])
    rev = ASSOC.get((t, f), [])
    for i, (tid, _) in enumerate(fwd):
        if tid == type_id and i < len(rev):
            return rev[i][0]
    return rev[0][0] if rev else type_id


def assoc_label(type_id):
    info = TYPE_ID_INFO.get(type_id)
    return info[2] if info else None


def assoc_type_name(f, t):
    return f"{SINGULAR_OF.get(f, f)}_to_{SINGULAR_OF.get(t, t)}"
