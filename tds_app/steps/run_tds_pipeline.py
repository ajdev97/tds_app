import os
import subprocess
import sys

steps = [
    (
        "Step 1: Mapping Ledgers to TDS Sections using OpenAI GPT",
        "step1_tds_section_mapper.py",
    ),
    ("Step 2: Preparing Processed Expense Data", "step2_prepare_expense_data.py"),
    ("Step 3: TDS Payable Reconciliation", "step3_tdspayable_reco.py"),
    ("Step 4: Parse 26Q and Extract TDS Details", "step4_parse_26q.py"),
    ("Step 5: Final TDS Reconciliation & Output", "step5_tds_reconciliation.py"),
]


def run_step(script_path, step_number, step_title):
    print(f"\n▶ Step {step_number}: {step_title}")
    print(f"\n▶ Running {os.path.basename(script_path)}...\n")

    process = subprocess.Popen(
        [sys.executable, script_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    for line in process.stdout:
        print(line, end="")
    process.wait()

    while True:
        choice = (
            input("\n⏭ Do you want to continue to the next step? (y/n/retry): ")
            .strip()
            .lower()
        )
        if choice == "y":
            return
        elif choice == "retry":
            run_step(script_path, step_number, step_title)
            return
        elif choice == "n":
            print("🛑 Exiting the pipeline.")
            sys.exit(0)
        else:
            print("Please enter 'y', 'n', or 'retry'.")


def main():
    for i, (desc, script) in enumerate(steps, start=1):
        run_step(script, i, desc)

    print("\n✅ All steps completed successfully.")


if __name__ == "__main__":
    main()
