# Multi-Agent Banking Intelligence System

A multi-agent banking prototype built with **Google's Agent Development Kit (ADK)** and the **Agent-to-Agent (A2A)** protocol. A front-desk manager agent routes customers to isolated deposit and loan agents, and new loan requests go through a deterministic approval pipeline.

The code lives in [`project/`](project). Setup, environment variables and run commands are in [`project/README.md`](project/README.md), and the executive report is in [`project/final_report.md`](project/final_report.md).

---

## System Architecture

The system segregates banking data and workflows across three independent agents connected via A2A:

```mermaid
flowchart TD
    Customer([Customer]) -->|Inquiry| Manager[Manager Agent: bank_agent<br/>Model: gemini-2.5-flash<br/>Port 8000 /a2a/manager]
    
    Manager -->|Direct General FAQ| FAQ[Operating Hours, Locations, Support]
    Manager -->|A2A: Deposit Inquiries| Deposit[Deposit Account Agent<br/>deposit_account_agent<br/>Model: gemini-2.5-pro]
    Manager -->|A2A: Loan Inquiries & Requests| Loan[Loan Account Agent<br/>loan_account_agent<br/>Model: gemini-2.5-pro]
    
    Deposit <-->|MCP Toolbox| DepDB[(bank.accounts<br/>bank.transactions)]
    Loan <-->|MCP Toolbox| LoanDB[(bank.loans)]
    
    subgraph LoanApprovalPipeline ["Loan Approval Orchestrator (loan_approval_agent)"]
        Loan -->|New Loan Request| S1[loan_approval_data_agent<br/>SequentialAgent]
        S1 --> S2[loan_approval_policy_agent<br/>LlmAgent via GCS PDF]
        S2 --> S3[loan_approval_review_agent<br/>ParallelAgent]
        
        subgraph ParallelBranches ["Parallel Execution"]
            S3 --> UPA[loan_approval_user_profile_agent<br/>LlmAgent via GCS PDF]
            S3 --> DEA[loan_approval_debt_equity_agent<br/>SequentialAgent]
            DEA --> TVA[TotalValueAgent<br/>Custom Python Math Agent]
            TVA -->|A2A check-minimum-balance| Deposit
        end
        
        S3 --> S4[loan_approval_report_agent<br/>LlmAgent - gemini-2.5-pro]
    end
```

---

## Screenshots

### Deposit agent: balance lookup and total-balance guardrail
`get_balance` returns the vacation account balance. When asked for the total on deposit, the agent calls `get_accounts` but refuses to add the balances together.

![Deposit balance and guardrail](./screenshots/1_deposit_balance_and_guardrail.png)

### Manager agent: routing between deposit and loan agents
The manager answers a transaction question through the deposit agent, then uses `transfer_to_agent` to hand an auto-payment question to the loan agent, which calls `get_loan_info`.

![Manager routing](./screenshots/2_manager_agent_routing.png)

### Loan approval: approved request
The pipeline writes `user_profile` and `check_equity` to state, and `loan_approval_report_agent` approves a $10,000 auto loan.

![Loan approved](./screenshots/3_loan_approval_success_state.png)

### Loan approval: rejected request
A $50,000 request is declined. The customer only gets a respectful notice, with no credit rating or internal ratios disclosed.

![Loan rejected](./screenshots/4_loan_approval_rejected_state.png)

### A2A batch evaluation
`testing/bin/a2a.py` sends the 18 scenario messages in `test_scenarios.csv` to the manager over A2A.

![A2A test suite](./screenshots/5_a2a_test_suite_execution.png)

### Unit tests
All 21 unit tests pass.

![Unit tests](./screenshots/6_automated_unit_tests.png)

---

## Security & Privacy Guardrails

1. **Total Balance Prohibition**: In compliance with banking security standards, the deposit agent strictly refuses to output total aggregate balances across accounts, mitigating unauthorized asset reconnaissance (`msg-003-1`).
2. **Rejection Privacy Enforcement**: When an application is declined (`msg-007-2`), the loan approval pipeline generates a respectful, general notification without disclosing proprietary credit ratings, debt ratios, or internal bank formulas.
3. **Deterministic Math**: The custom `TotalValueAgent` computes required minimum deposit balances using Python floating-point arithmetic, entirely eliminating LLM hallucination risks during financial underwriting.
