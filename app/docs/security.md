# Security & Bug Bounty

## Our commitment

Casual Heroes is a small indie gaming community, and we take security seriously. If you find something broken, we want to know - and we want you to feel safe telling us.

We're not a big corporation. We don't have a legal team. What we do have is a genuine commitment to fixing issues quickly, being transparent with you, and giving real credit to people who help us improve.

Email us at [security@casual-heroes.com](mailto:security@casual-heroes.com).

---

## Safe harbour

If you follow this policy and act in good faith, we will not pursue legal action against you for your security research. We consider responsible testing conducted within scope to be authorised activity.

We won't file complaints with law enforcement against researchers who act within scope and in good faith.

**Limits.** Safe harbour does not cover research done for extortion or coercion, activity that intentionally harms users or destroys data, or anything that goes beyond what's needed to demonstrate the vulnerability. If you're unsure whether something is okay to test, email us first.

---

## What's in scope

- Everything at `casual-heroes.com` and `dashboard.casual-heroes.com`, including all subdomains
- The QuestLog platform - accounts, profiles, posts, social features, communities
- The Discord and Fluxer bot dashboards
- Login, registration, session handling, and any flow that touches user data or permissions

Not sure if something is in scope? Ask us before testing.

---

## What's out of scope

- Anything we don't control. This includes all third-party services and integrations - Discord, Fluxer, Steam, Cloudflare, Stripe, Element, Matrix.org, and any other external provider. If you find something in a third-party service, report it to them directly
- Physical access to hardware or facilities
- Social engineering or phishing of our staff or community members
- Flooding, denial-of-service, or any testing that degrades the service for other users. Exception: if you find a single unauthenticated request that can take something down, report it without actually doing it at scale
- General bugs or feature requests - those go to [support@casual-heroes.com](mailto:support@casual-heroes.com)
- Theoretical issues with no realistic exploitation path

---

## How to report

Email **[security@casual-heroes.com](mailto:security@casual-heroes.com)** with:

- What the issue is and what an attacker could do with it
- Step-by-step instructions to reproduce it
- Screenshots, HTTP requests, or any proof of concept that helps us understand it
- What account type or setup you used

The more detail you include, the faster we can fix it.

---

## Disclosure timeline

Please don't post about the vulnerability publicly until we've had a chance to fix it.

We aim to acknowledge your report within **3 business days** and to fix confirmed vulnerabilities within **90 days**. We'll keep you updated as we work on it. Once it's fixed, we'll coordinate a public disclosure with you and credit you unless you'd prefer to stay anonymous.

If we need more time than 90 days, we'll tell you why and agree on a new timeline with you. We won't ask for indefinite silence.

---

## What you get

We can't offer cash bounties right now, but we do offer real recognition.

| Severity | What we offer |
|----------|---------------|
| Critical | Hall of Fame, 1 year Champion, social media shoutout |
| High | Hall of Fame, 6 months Champion |
| Medium | Hall of Fame, 3 months Champion |
| Low | Hall of Fame listing |

**Champion** is our supporter subscription - it's how we say thank you with something that has real value on the platform. If a finding is exceptional we may go above the tier. Cash rewards are something we want to introduce as the platform grows - we'll update this page when that changes.

To be eligible you need to report privately, not exploit beyond what's needed to demonstrate the issue, and not publicly disclose before we've fixed it.

---

## How we handle reports

- **Within 3 business days** - we acknowledge your report
- **Within 5 business days** - we give you an initial assessment
- **Ongoing** - we keep you updated as we investigate and fix
- **After the fix** - we coordinate disclosure and credit with you

If we can't reproduce the issue we'll tell you what we tried and work with you to figure it out. We won't just close it.

---

## Safe testing rules

- Only test accounts and data you own or have explicit permission to use
- If you accidentally access another user's data, stop immediately, don't save or share it, and tell us
- Don't delete or modify other users' data
- Don't send notifications or messages to users who aren't part of your test
- Handle any user data you encounter securely and delete it when your research is done

---

## Hall of Fame

Researchers who responsibly disclose vulnerabilities are listed on our [Security Hall of Fame](/security/hall-of-fame/) with their consent.

---

*Last updated: March 2026*
