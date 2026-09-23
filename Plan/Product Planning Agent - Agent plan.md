I want to build a **Product Planning Agent** based on a short, high-level requirement provided by the user.

The agent's first responsibility will be to **understand and clarify the user's requirement** through a structured question-and-answer process. Instead of immediately creating a plan, the agent should ask relevant questions to understand the complete product idea, goals, scope, expected behavior, constraints, user flows, and business or technical requirements.

The agent should not assume that the user already knows the answer to every question. The clarification process should be designed to help the user discover and define the requirement, rather than simply collect predefined answers.

Once the requirement is sufficiently clear, the agent should perform the necessary **research and analysis** and guide the user through creating a complete product plan.

---

## 1. Requirement Clarification

The agent should analyze the initial requirement and determine:

- What information is already known
    
- What information is missing
    
- Which information is critical
    
- Which information can be researched
    
- Which decisions require input from the user
    
- Which questions can be postponed
    
- Which assumptions may be safely made
    
- Which unknowns prevent the agent from continuing
    

The agent should ask only relevant questions and should avoid asking questions for information that has already been provided.

The clarification process should continue until the agent has enough information to confidently begin research and planning.

---

## 2. Every Question Must Have an "I Don't Know" Path

The user may not know the answer to a question asked by the agent. Therefore, **"I don't know" must be a valid response to every question**.

The agent should never treat "I don't know" as a failure or force the user to provide an answer they do not have.

When the user responds with "I don't know", the agent should determine what to do next.

Possible actions include:

- Provide guidance
    
- Explain why the decision matters
    
- Present possible options
    
- Research the available options
    
- Ask simpler follow-up questions
    
- Make a temporary assumption
    
- Mark the item as an open decision
    
- Allow the user to decide later
    

This allows the agent to act as a **product planning partner**, rather than just a questionnaire.

---

## 3. Question Mode → Guidance Mode

When the user does not know how to answer a question, the agent should be able to switch from **Question Mode** to **Guidance Mode**.

Guidance Mode should be implemented as a dedicated tool or capability that helps the user understand the decision they need to make.

The Guidance Tool should be able to:

- Explain the question in simple terms
    
- Explain why the decision is important
    
- Identify areas the user should consider
    
- Provide possible options
    
- Compare different options
    
- Identify trade-offs
    
- Suggest actions the user should take
    
- Identify areas that could be improved
    
- Recommend what information is required before making a decision
    
- Perform or request research when appropriate
    
- Help the user reach a decision
    

For example, if the agent asks:

> Who is the primary target user?

and the user responds:

> I don't know.

The agent should not simply ask another unrelated question. Instead, it should activate Guidance Mode and help the user identify potential users based on the problem, workflow, and product context.

The Guidance Tool should therefore help transform:

**"I don't know" → Understanding → Options → Decision**

---

## 4. Support "Decide Later"

The user should be able to explicitly choose:

**"Decide Later"**

when a decision cannot or does not need to be made immediately.

However, "Decide Later" must be tracked as a structured decision state rather than simply ignored.

Each deferred decision should contain relevant timeline information, such as:

- Decision ID
    
- Decision/question
    
- Current status
    
- Date it was identified
    
- Date it was created
    
- Expected decision date
    
- Actual decision date
    
- Current owner
    
- Reason for postponing the decision
    
- Related requirement
    
- Related plan section
    
- Whether the decision is blocking or non-blocking
    
- What needs to happen before the decision can be made
    

For example:

```text
Decision: Database Selection

Status: Decide Later

Identified: 2026-09-21
Expected Decision Date: 2026-09-25
Decision Date: TBD

Reason:
Additional technical requirements are still being researched.

Blocking:
No

Owner:
Product/Engineering

Related Requirement:
REQ-018
```

The agent should use dates and timestamps throughout the planning process so that future decisions, changes, and planning activities have a clear historical reference.

This should allow the system to answer questions such as:

- When was this decision first identified?
    
- When did we decide to postpone it?
    
- When was the decision eventually made?
    
- What did we know at the time?
    
- Which plan version was active when the decision was made?
    
- How did the decision affect the timeline?
    

---

## 5. Separate Required Unknowns from Optional Unknowns

Not every unknown should prevent the agent from continuing.

The agent should classify unknowns based on their impact on the planning process.

The core rule should be:

> **Does this unknown prevent us from continuing?**

If **yes**, the agent should clarify, research, or resolve it before proceeding.

If **no**, the agent should record it as an open question, assumption, or future decision and continue planning.

For example:

|Question|User doesn't know|What the agent should do|
|---|---|---|
|Who is the target user?|Yes|Help the user determine it|
|What problem are we solving?|Yes|Explore with the user before continuing|
|Which database should we use?|Yes|Research and recommend suitable options|
|Exact UI color?|Yes|Mark as an open decision|
|Expected traffic?|Yes|Estimate or research later|
|Deployment provider?|Yes|Research possible options|
|Pricing model?|Yes|Mark as a product decision|

The agent should distinguish between:

- **Blocking Unknown**
    
- **Non-Blocking Unknown**
    
- **Research Required**
    
- **User Decision Required**
    
- **Optional Decision**
    
- **Future Decision**
    

This classification should determine the next action of the agent.

---

## 6. Assumptions Must Never Be Silent

The agent may need to make assumptions in order to continue planning, but it must **never make an assumption silently**.

Every assumption should be explicitly recorded and visible to the user.

For example:

```text
Assumption ID: ASM-014

Assumption:
The initial version will support web only.

Created:
2026-09-21

Source:
Agent

Reason:
No mobile application requirement has been provided.

Confidence:
72%

Impact:
Medium

Status:
Pending Review

User Confirmation Required:
Yes
```

The user should be able to:

- Confirm the assumption
    
- Reject the assumption
    
- Modify the assumption
    
- Convert it into a confirmed requirement
    
- Mark it for later review
    

The system should also track which parts of the plan depend on each assumption.

Before the plan is finalized, the agent should review important assumptions with the user.

---

## 7. Confidence and Status for Every Important Requirement

Every important requirement, assumption, decision, or planning item should have a structured status and confidence level.

Possible statuses could include:

- `CONFIRMED`
    
- `PROPOSED`
    
- `ASSUMED`
    
- `UNKNOWN`
    
- `OPEN_DECISION`
    
- `DECIDE_LATER`
    
- `RESEARCH_REQUIRED`
    
- `BLOCKED`
    
- `RESOLVED`
    
- `REJECTED`
    
- `SUPERSEDED`
    

The agent should also maintain a confidence level where appropriate.

For example:

```text
Requirement:
Users can invite team members to a project.

Status:
PROPOSED

Confidence:
85%

Source:
User clarification

Requires Confirmation:
Yes
```

This allows the agent to distinguish between something the user explicitly confirmed and something the agent inferred or proposed.

---

## 8. Version Control and Requirement History

Requirements should be version-controlled.

A requirement should not simply be overwritten when it changes.

For example:

```text
REQ-001 v1
Users can create projects.

REQ-001 v2
Authenticated users can create projects.

REQ-001 v3
Authenticated users can create projects
and invite team members.
```

Every change should maintain:

- Requirement ID
    
- Version
    
- Previous version
    
- New version
    
- Changed fields
    
- Change reason
    
- Changed by
    
- Date/time of change
    
- Source of the change
    
- Impact of the change
    

The system should maintain a complete history so that the agent can answer:

> What changed?

> When did it change?

> Why did it change?

> Who confirmed the change?

> What parts of the plan were affected?

---

## 9. Version Control for the Product Plan

The same versioning approach should apply to the overall product plan.

For example:

```text
PLAN v1
Initial plan

PLAN v2
Updated after authentication decision

PLAN v3
Updated after mobile requirement was added
```

When an important requirement or decision changes, the agent should perform **impact analysis**.

For example:

```text
Requirement Changed
        ↓
Impact Analysis
        ↓
Affected Requirements
        ↓
Affected Decisions
        ↓
Affected Architecture
        ↓
Affected Timeline
        ↓
Affected Plan Sections
        ↓
Affected Stories
```

The agent should identify what needs to be reviewed rather than blindly regenerating the entire plan.

---

## 10. Periodic Summary of Unknowns and Open Items

The agent should continuously track unresolved items and periodically summarize them for the user.

The system should maintain a **Planning Status** that can be generated at any point.

For example:

```text
PROJECT PLANNING STATUS

Planning Progress: 68%

Requirements
✓ 14 Confirmed
⚠ 3 Assumptions
? 2 Unknowns
⏳ 2 Decisions Pending

Blocking Issues
🔴 1

Research
✓ 8 Completed
⏳ 2 In Progress

Plan
Draft v3

Timeline
Start: 2026-09-21
Target: 2026-10-18
```

The agent should also provide an Open Items list:

```text
1. Target user confirmation
   Type: Blocking
   Owner: User
   Due: 2026-09-22

2. Authentication approach
   Type: Decision
   Owner: User
   Due: 2026-09-24

3. Database selection
   Type: Research
   Owner: Agent
   Due: 2026-09-23

4. Mobile support
   Type: Optional
   Owner: User
   Due: TBD
```

This tracking mechanism should allow the agent to periodically remind the user about unresolved items and identify items that are approaching their expected decision date.

---

## 11. Planning Ledger / Source of Truth

The agent should maintain a central **Planning Ledger** as the source of truth for the entire project.

The ledger should contain:

- Requirements
    
- Requirement versions
    
- Questions
    
- Answers
    
- Unknowns
    
- Assumptions
    
- Decisions
    
- Deferred decisions
    
- Research findings
    
- Risks
    
- Dependencies
    
- Timeline
    
- Milestones
    
- Plan versions
    
- Change history
    
- Impact analysis
    
- Generated stories
    

The LLM should not rely only on conversation history to remember these details.

Instead, the workflow should be:

**Read Planning Ledger → Analyze Current State → Take Action → Update Planning Ledger**

This provides consistency, traceability, and long-term context.

---

## 12. Product Understanding and Planning

Once the requirement has been sufficiently clarified, the agent should help define:

- What exactly needs to be built
    
- The overall product vision and objectives
    
- The problem being solved
    
- Target users
    
- Key features and functionality
    
- User journeys and workflows
    
- How the website or product should work
    
- Important user actions
    
- Functional requirements
    
- Non-functional requirements
    
- Technical considerations
    
- Architecture considerations
    
- API and data requirements
    
- Dependencies
    
- Risks
    
- Security considerations
    
- Performance considerations
    
- What needs to be built first
    
- What can be deferred
    
- Milestones and phases
    
- Estimated development timeline
    
- Open decisions
    
- Assumptions
    
- Research requirements
    
- Testing requirements
    
- Rollout considerations
    

The agent should continuously refine and validate the plan until it reaches a **complete and actionable state**.

---

## 13. Research and Decision Support

The agent should be able to identify when research is required rather than asking the user to answer something they may not know.

For example:

> Which database should we use?

If the user says:

> I don't know.

The agent can determine that this is a **Research Required** item and investigate suitable options based on the product requirements.

The research should then become part of the Planning Ledger and should be connected to the resulting decision.

This creates a flow such as:

**Unknown → Research → Options → Trade-offs → User Decision → Confirmed Requirement**

---

## 14. Timeline and Milestones

The agent should create a timeline based on the completed scope and planning information.

The timeline should include:

- Planning start date
    
- Requirement clarification dates
    
- Research dates
    
- Decision deadlines
    
- Milestones
    
- Development phases
    
- Dependencies
    
- Expected completion dates
    
- Deferred decision dates
    
- Plan revision dates
    

The timeline should also change when major requirements change.

For example:

```text
Requirement Changed
        ↓
Impact Analysis
        ↓
Scope Changed
        ↓
Timeline Recalculated
        ↓
Affected Milestones Updated
```

All timeline changes should be versioned so the system can understand how and why the timeline changed.

---

## 15. Final Plan → Stories

Once the product plan has been completed and the critical requirements, assumptions, and decisions have been reviewed, the agent should break the plan down into **small, well-defined stories** for each feature, bug, issue, or development task.

Each story should be:

- Clear and concise
    
- Independently understandable
    
- Actionable for developers or team members
    
- Based directly on the finalized product plan
    
- Traceable to the requirement that created it
    
- Traceable to the relevant plan version
    
- Suitable for adding to a project-management or issue-tracking tool
    

Each story should ideally contain:

- Story ID
    
- Title
    
- Description
    
- Requirement reference
    
- Plan reference
    
- Acceptance criteria
    
- Dependencies
    
- Priority
    
- Relevant technical notes
    
- Assumptions, if any
    
- Related decisions
    
- Expected effort or estimation, where applicable
    

The stories should be generated from the **completed and approved plan**, rather than directly from the user's initial request.

---

## 16. Change and Impact Management

The agent should be able to handle changes after the plan has already been created.

For example, if the user says:

> We also need a mobile application.

The agent should not simply append this as another requirement.

It should:

1. Create a new requirement version.
    
2. Identify affected requirements.
    
3. Identify affected assumptions.
    
4. Identify affected decisions.
    
5. Perform impact analysis.
    
6. Update the product scope.
    
7. Recalculate the timeline where necessary.
    
8. Create a new plan version.
    
9. Identify affected stories.
    
10. Mark those stories for review or regeneration.
    

This ensures that the planning system remains consistent as the product evolves.

---

## 17. Overall Workflow

The complete workflow should therefore be:

**Short Requirement**  
↓  
**Initial Product Understanding**  
↓  
**Clarification Q&A**  
↓  
**Unknown Detection**  
↓  
**Guidance / Research / Decision Support**  
↓  
**Requirements & Assumptions Tracking**  
↓  
**Decision Management**  
↓  
**Requirement Confirmation**  
↓  
**Research & Analysis**  
↓  
**Product Planning**  
↓  
**Milestones & Timeline**  
↓  
**Plan Review**  
↓  
**Plan Approval / Completion**  
↓  
**Feature / Bug / Issue Story Generation**  
↓  
**Project Management / Issue Tracking Tool**

This workflow should remain dynamic rather than strictly linear because new information, decisions, or requirements can appear at any stage.

---

## 18. Core Objective

The main challenge I want to solve first is the **requirement clarification and planning intelligence layer**.

I want to design a question-and-answer-based interaction pattern that enables the agent to intelligently determine:

1. What it already knows from the user's initial requirement.
    
2. What information is missing.
    
3. Which questions need to be asked.
    
4. Which questions are important enough to ask.
    
5. Which unknowns are blocking and which are non-blocking.
    
6. When to switch from Question Mode to Guidance Mode.
    
7. When to perform research instead of asking the user.
    
8. When to allow the user to decide later.
    
9. How to track deferred decisions and their dates.
    
10. How to make assumptions without hiding them from the user.
    
11. How to track the confidence and status of every important requirement.
    
12. How to maintain complete version history for requirements and plans.
    
13. How to track changes and perform impact analysis.
    
14. How to periodically summarize unresolved questions, assumptions, decisions, and risks.
    
15. How to maintain a central Planning Ledger as the source of truth.
    
16. When the requirement has been clarified sufficiently.
    
17. When the agent has enough information to begin research and planning.
    
18. How to maintain context throughout multiple rounds of Q&A.
    
19. How to convert clarified requirements into a complete product plan.
    
20. How to determine milestones and an estimated timeline based on the scope.
    
21. How to continuously update the plan as requirements change.
    
22. How to convert the completed plan into small, implementation-ready stories.
    

The final goal is to build a reusable **Product Planning Agent** that can take a simple idea or high-level requirement and guide the user from the initial concept all the way to a **complete, traceable, version-controlled, actionable product plan**, and finally generate **implementation-ready stories** that can be added to any project-management or issue-tracking tool.

The agent should ultimately behave less like a simple chatbot or questionnaire and more like a **Product Analyst + Requirements Engineer + Research Assistant + Planning Agent + Decision Management System**.