document.addEventListener("DOMContentLoaded", () => {
  const forms = document.querySelectorAll("form.upload-form");

  forms.forEach((form) => {
    const submitButton = form.querySelector("button[type='submit']");
    const fileInput = form.querySelector("input[type='file']");

    let status = form.querySelector(".form-status");
    if (!status) {
      status = document.createElement("p");
      status.className = "form-status muted";
      status.setAttribute("aria-live", "polite");
      form.appendChild(status);
    }

    if (submitButton) {
      submitButton.disabled = false;
    }

    form.addEventListener("submit", (event) => {
      if (fileInput && fileInput.required && (!fileInput.files || fileInput.files.length === 0)) {
        event.preventDefault();
        status.textContent = "Choose a file first, then tap the upload button.";
        if (submitButton) {
          submitButton.disabled = false;
        }
        return;
      }

      status.textContent = "Uploading. Please keep this page open.";

      if (submitButton) {
        submitButton.disabled = true;
        submitButton.dataset.originalText = submitButton.textContent || "Upload";
        submitButton.textContent = "Uploading...";
      }
    });
  });
});
