# SmartBank Retail Loan Policy

*Fictional document created for the SmartBank AI demo. Version 3.2, effective 1 April 2026.*

## Loan products and limits
SmartBank offers four retail loan products to resident Indian customers aged 21 to 60:
- **Personal Loan**: tenure 12 to 60 months; maximum amount 20 times net monthly income; no collateral.
- **Car Loan**: tenure 12 to 84 months; maximum amount 30 times net monthly income; up to 90% of the on-road price; the vehicle is hypothecated to the bank.
- **Home Loan**: tenure up to 360 months; maximum amount 80 times net monthly income; loan-to-value up to 80% of the property value.
- **Education Loan**: tenure up to 120 months including a moratorium of course period plus 6 months; maximum amount 40 times household monthly income.

## Eligibility criteria
An application is assessed automatically by the Loan Origination System using the following rules:
1. **KYC** must be in VERIFIED status. Applications from customers with pending KYC are not processed.
2. **Credit score** (bureau score on a 300-900 scale) minimums: Personal 700, Car 680, Home 700, Education 650. Customers with no credit history cannot be approved automatically and are referred to a branch.
3. **Repayment track record**: two or more missed payments in the last 12 months lead to automatic decline.
4. **FOIR (Fixed Obligation to Income Ratio)**: the total of all EMIs, including the new loan, must not exceed **50%** of net monthly income.

When an applicant passes the score checks but the requested amount breaches the FOIR or income-multiple limit, the application is marked **CONDITIONAL** and the customer is offered the maximum eligible amount.

## Interest rates
Rates are linked to the credit score band (annual, reducing balance):

| Product | 780 and above | 740-779 | 700-739 | below 700 |
|---|---|---|---|---|
| Personal | 11.00% | 11.75% | 12.50% | 13.50% |
| Car | 9.00% | 9.75% | 10.50% | 11.50% |
| Home | 8.50% | 9.25% | 10.00% | 11.00% |
| Education | 9.50% | 10.25% | 11.00% | 12.00% |

## EMI calculation
EMI is computed with the standard reducing-balance formula: EMI = P x r x (1+r)^n / ((1+r)^n - 1), where P is the principal, r is the monthly interest rate (annual rate / 12 / 100) and n is the tenure in months.

## Processing fees
- Personal Loan: 1.5% of the loan amount, minimum Rs 1,999, plus GST.
- Car Loan: 1% of the loan amount, maximum Rs 10,000, plus GST.
- Home Loan: 0.5% of the loan amount, maximum Rs 15,000, plus GST.
- Education Loan: nil.

## Prepayment and foreclosure
- **Floating-rate Home Loans** and all loans to individuals for non-business purposes on floating rates: no prepayment or foreclosure charges.
- **Personal Loans**: part-prepayment is allowed after 12 EMIs, up to 25% of outstanding principal per year, free of charge. Full foreclosure after 12 EMIs carries a 3% charge on outstanding principal; before 12 EMIs foreclosure is not permitted.
- **Car Loans**: foreclosure after 6 EMIs with a 4% charge on outstanding principal (2% after 24 EMIs).
- **Education Loans**: no prepayment charges at any time.

## Late payment
A missed EMI attracts a penal charge of 2% per month on the overdue amount (minimum Rs 500), and is reported to credit bureaus after 30 days past due. Bounce charges of Rs 500 apply per failed auto-debit (NACH) mandate.

## Application process
Pre-approved customers can apply directly in the SmartBank app. Every application requires explicit confirmation by the customer in the app. After submission, the customer receives a reference number (format SB-LN-XXXXX); disbursal typically happens within 2 working days for personal loans and 5 working days for car loans after document verification.
