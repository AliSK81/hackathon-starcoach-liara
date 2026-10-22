**System Description — Liara Website Setup, Deploy & Monitoring Assistant Challenge**

The system is an intelligent assistant that acts as a technical collaborator for website owners — from first deploy and resource selection through continuous monitoring, problem diagnosis, and helping maintain service stability — so the user focuses on developing and improving their product instead of infrastructure complexity. The challenge video is mandatory viewing and, together with the text, defines the problem, requirements, and how to do the challenge.

**Expected Capabilities**

*Initial Setup & Deployment*
- Guide the user to choose the appropriate deployment and initial setup method.
- Review project requirements and suggest suitable Liara infrastructure and plan matching the project type and required resources.
- Help with initial setup, configuration, and deploy steps.
- Guide domain setup and the required steps in the domain registrar panel (e.g., IRNIC) where needed.
- Simplify setup so the user performs only essential steps outside the assistant's reach.

*Deployment & Operations*
- Help publish new website versions.
- Perform or guide configuration and service management via Liara APIs.
- Check service status and identify possible errors in the deploy process.
- Automate repetitive operations and reduce the need for manual technical steps.

*Monitoring & Maintenance*
- Check service health and resource consumption, including CPU and RAM, where the relevant data is accessible.
- Retrieve and analyze service-related logs.
- Help investigate issues such as website slowdown, malfunction, or increased resource usage.
- Provide suggestions to improve performance and stability.
- Take corrective action or guide the user to fix the problem.

*Intelligent Troubleshooting*
On errors such as HTTP 500, the assistant can:
- Gather error-related information from available sources.
- Check logs, service status, and resource-consumption data.
- Identify and prioritize probable causes.
- Provide a suitable fix.
- If authorized, take corrective action and check the result.

Example: if the website is slow, the assistant can examine available evidence to determine whether increased RAM usage, CPU limits, application errors, or another factor is likely, then suggest a suitable remedy.

*Human-in-the-Loop*
For sensitive or high-consequence operations, the assistant obtains user confirmation before execution — including risky configuration changes, service restart, or plan/resource changes. The solution distinguishes low-risk operations executable automatically from sensitive operations requiring user approval. Operation results and possible errors are visible to the user.

**Technical Constraints and Available Tools**
| Topic | Description |
|---|---|
| Liara APIs | Use Liara APIs to retrieve required information and perform infrastructure operations. |
| Implementation approach | AI Agent, MCP, or a combination. |
| User interface | Custom UI, conversational interface, CLI, or other interaction methods. |
| Architecture choice | Architecture, tools, and implementation are the participants' choice. |
| API access limits | API use follows Liara's actually available capabilities; where certain information or operations are unavailable via API, the solution clearly informs the user of the limitation. |

**Product Design Notes and Requirements**

*UX*
Simplicity and ease of use for the end user are among the most important criteria. Implementing technical capabilities alone is insufficient; the solution turns complex infrastructure operations into a simple, understandable, and trustworthy experience. The user can:
- State their request with minimal technical knowledge.
- Understand operation status.
- Evaluate the assistant's suggestions.
- Approve execution of operations where needed.

*Expected output* — depends on participant choice: agent, MCP, etc.

**Deliverables**

*Required output and documentation*
A runnable MVP covering a defined part of the website setup, deploy, or maintenance cycle. The MVP, besides showing technical capabilities, demonstrates a real scenario from user request through operation or problem diagnosis. An MD document is saved in GitHub including:
- Brief architecture documentation.
- How to connect to Liara APIs.
- Solution limitations.
- How the user interacts with the system.

*Demo video (mandatory)*
- Submitting a project demo video is mandatory.
- The video is about 5 minutes and demonstrates and explains the project's performance.
- If no demo video is submitted, the entry is removed from judging.
- Video quality affects the overall score.
- The video shows the output; no need to show source code. Performance, impact, output, and demonstrable items matter. The work is presented completely — this is very important.
- If unable to speak, a silent video of the output only is acceptable but scores fewer points; this is better than no points. No special editing is needed.

**Judging Criteria (300 points)**

*Technical performance and Liara integration — 100*
- Connection to Liara APIs
- Setup and deploy
- Service management
- Successful execution of infrastructure operations

*Intelligence and problem-solving ability — 100*
- Log analysis
- Error detection
- Identification of probable causes
- Providing solutions
- Checking the result of corrective actions

*User experience — 50*
- Simplicity of interaction
- Understandability of suggestions
- Display of operation status
- User-approval management for sensitive actions

*Stability, maintenance, and operational security — 50*
- Service and resource health monitoring
- Automation of repetitive operations
- Secure handling of sensitive actions
- Disclosure of API limitations

**Scoring Table**
| # | Criterion | Evaluated items | Points |
|---|---|---|---|
| 1 | Technical performance and Liara integration | Connection to Liara APIs, setup and deploy, service management, successful execution of infrastructure operations | 100 |
| 2 | Intelligence and problem-solving ability | Log analysis, error detection, identification of probable causes, providing solutions, checking the result of corrective actions | 100 |
| 3 | User experience (UX) | Simplicity of interaction, understandability of suggestions, display of operation status, user-approval management for sensitive actions | 50 |
| 4 | Stability, maintenance, and operational security | Service and resource health monitoring, automation of repetitive operations, secure handling of sensitive actions, disclosure of API limitations | 50 |
| | **Total** | | **300** |