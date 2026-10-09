# AI Job Pilot - Q&A Testing Plan

**Date**: May 7, 2026  
**Status**: Ready for execution once search completes

## Test Execution Order

### 1. Dashboard Statistics (`/`)
✅ **Objective**: Verify dashboard loads and displays correct statistics

- [ ] Dashboard page loads without errors
- [ ] Stats cards are visible (Total Found, Total Matched, Total Applications)
- [ ] Job counts match database counts
- [ ] "Last Run" timestamp is displayed and is recent
- [ ] All stats update when data changes

**API Endpoints to Verify**:
- GET `/api/jobs/stats/summary` → Returns: `{"total_found": N, "total_matched": N, "total_applied": N, "by_source": {...}, "by_status": {...}}`

---

### 2. Job Listing & Filtering (`/jobs`)
✅ **Objective**: Verify jobs display correctly with all filtering options

- [ ] Jobs page loads and displays job list
- [ ] All job fields render correctly (title, company, location, match score)
- [ ] Jobs are sorted by match score (highest first)
- [ ] Pagination works (page changes, limit changes)

**Filter Tests**:
- [ ] Filter by status (found, matched, draft_ready, email_sent, applied, rejected, interview, offer, skipped)
- [ ] Filter by source (linkedin, indeed, top_companies)
- [ ] Filter by minimum match score
- [ ] Search by job title or company name
- [ ] Filters work in combination

**API Endpoint to Test**:
- GET `/api/jobs?page=1&limit=20&status=matched&source=linkedin&min_score=0.7&search=engineer`

---

### 3. Individual Job Details (`/jobs/:id`)
✅ **Objective**: Verify job detail view and actions

- [ ] Job detail page loads
- [ ] All job information displays (title, company, location, salary, description, match score)
- [ ] Match reasons are displayed
- [ ] Skills matched and missing are shown
- [ ] Job URL links to original posting
- [ ] Status can be updated from detail view

**API Endpoint to Test**:
- GET `/api/jobs/{job_id}`
- PATCH `/api/jobs/{job_id}/status` with status parameter

---

### 4. Email Management (`/emails`)
✅ **Objective**: Verify draft emails and sending

- [ ] Email drafts list displays
- [ ] Subject and preview show correctly
- [ ] Can view full email body
- [ ] Can edit draft email text
- [ ] Can send email manually
- [ ] Sent emails move to sent folder
- [ ] Email status updates correctly

**Expected Actions**:
- Draft emails should be created for matched jobs (score >= min_match_score)
- To address should be populated or suggest hiring manager name
- Subject should be personalized
- Body should reference job title and company

**API Endpoints to Test**:
- GET `/api/emails` → List drafts
- GET `/api/emails/{email_id}` → View email
- POST `/api/emails/{email_id}/send` → Send email

---

### 5. Applications Tracking (`/applications`)
✅ **Objective**: Verify application workflow

- [ ] Applications list displays
- [ ] Status shows correct stage (draft_ready, email_sent, applied, interview, offer)
- [ ] Can view application details
- [ ] Can update application status
- [ ] Follow-up dates are set correctly
- [ ] Application history is tracked

**Test Workflow**:
1. Create draft email for matched job
2. Send email → Application status should become "email_sent"
3. Update application status to "interview"
4. Verify status updates in both Applications and Jobs views
5. Follow-up date should be set to 7 days from send date

**API Endpoints to Test**:
- GET `/api/applications` → List applications
- GET `/api/applications/{app_id}` → View application
- PATCH `/api/applications/{app_id}` → Update status

---

### 6. Search & Automation
✅ **Objective**: Verify search triggering and automation

- [ ] Can manually trigger search from UI button
- [ ] Search progress is visible during execution
- [ ] Search completes and updates statistics
- [ ] New jobs are added without duplicates
- [ ] Duplicate jobs are filtered out in subsequent searches

**Auto-Send Testing** (if configured):
- [ ] Jobs with score >= auto_send_above_score are auto-sent
- [ ] Daily limit prevents over-sending
- [ ] Auto-sent emails are tracked correctly

**API Endpoint to Test**:
- POST `/api/jobs/search/trigger` → Trigger search manually

---

### 7. Settings & Preferences
✅ **Objective**: Verify profile and preferences are saved correctly

**Profile Settings**:
- [ ] Resume upload works
- [ ] Parsed fields populate correctly (name, email, skills, experience)
- [ ] Profile information saves
- [ ] Profile loads when page revisits

**Job Preferences**:
- [ ] Job titles can be added/removed
- [ ] Keywords and exclusions save
- [ ] Locations are normalized (verify "melbourne" → "Melbourne, Australia")
- [ ] Sources selection saves
- [ ] Match score thresholds save
- [ ] Auto-send threshold saves

**API Endpoints to Test**:
- PUT `/api/settings/profile` → Update profile
- POST `/api/settings/resume` → Upload resume
- PUT `/api/settings/preferences` → Update job preferences
- GET `/api/settings/preferences` → Verify saved preferences

---

## Test Data Expectations

After search completes:

```json
{
  "jobs_found": "N (1000+)",
  "jobs_matched": "M (>= N * 0.7)",  // Assuming min_match_score = 0.6
  "emails_drafted": "M",            // One draft per matched job
  "emails_sent": "0 or X",          // Depending on auto-send config
  "applications_created": "0 or X"   // One per sent email
}
```

---

## Performance Benchmarks

- Dashboard load: < 2 seconds
- Job list load: < 3 seconds
- Individual job detail: < 1 second
- Email drafting: < 30 seconds (Claude API call)
- Email sending: < 10 seconds (Gmail API call)
- Search completion: 15-30 minutes for 1000+ jobs

---

## Known Limitations

1. **Glassdoor**: Returns 403 errors (rate limiting) - not included in this search
2. **Seek.com.au**: Returns 403 errors - excluded for stability
3. **Web3.careers**: Timeout errors - excluded for stability
4. **Prosple**: Returns 403 errors - excluded for stability
5. **LinkedIn Invalid Locations**: jobspy encounters jobs with invalid locations like "afghanistan" - these cause scraping to skip some results but don't block the entire search

---

## Success Criteria

✅ All sections pass with no errors
✅ Dashboard displays accurate statistics
✅ Jobs filter and display correctly
✅ Emails draft and send successfully
✅ Applications track status correctly
✅ Recurring search works (every 6 hours by default)
✅ No SQL or API errors in logs

