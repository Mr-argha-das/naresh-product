const todayInputs = document.querySelectorAll('input[type="date"][name="date"]');
const today = new Date().toISOString().slice(0, 10);
todayInputs.forEach((input) => {
  if (!input.value) input.value = today;
});

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", () => {
    const button = form.querySelector('button[type="submit"]');
    if (button && !button.dataset.keepText) {
      button.dataset.originalText = button.textContent;
      button.textContent = "Working...";
      button.disabled = true;
    }
  });
});

document.querySelectorAll("[data-transaction-form]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    const credit = form.querySelector('[name="account_from"]');
    const debit = form.querySelector('[name="account_to"]');
    if (!credit || !debit || credit.value !== debit.value) return;

    event.preventDefault();
    const button = form.querySelector('button[type="submit"]');
    if (button) {
      button.textContent = button.dataset.originalText || "Save Pending Trnx";
      button.disabled = false;
    }
    alert("Debit account aur credit account alag choose karo.");
  });
});
