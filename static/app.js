document.addEventListener("DOMContentLoaded", () => {
  const uploadForms = document.querySelectorAll("form.upload-form");

  uploadForms.forEach((form) => {
    const submitButton = form.querySelector("button[type='submit']");
    const fileInput = form.querySelector("input[type='file']");
    let status = form.querySelector(".form-status");

    if (!status) {
      status = document.createElement("p");
      status.className = "form-status muted";
      status.setAttribute("aria-live", "polite");
      form.appendChild(status);
    }

    form.addEventListener("submit", (event) => {
      if (fileInput && fileInput.required && (!fileInput.files || fileInput.files.length === 0)) {
        event.preventDefault();
        status.textContent = "Choose a file first.";
        return;
      }

      status.textContent = fileInput ? "Uploading and analyzing…" : "Working…";
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.dataset.originalText = submitButton.textContent || "Submit";
        submitButton.textContent = fileInput ? "Uploading…" : "Working…";
      }
    });
  });

  document.querySelectorAll(".field-row input").forEach((input) => {
    input.addEventListener("input", () => {
      input.closest(".field-row")?.querySelector(".confidence")?.remove();
    });
  });
});
