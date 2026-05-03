document.addEventListener("DOMContentLoaded", () => {
  const forms = document.querySelectorAll("form.upload-form");

  forms.forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("button[type='submit']");
      if (button) {
        button.disabled = true;
        button.textContent = "Uploading...";
      }
    });
  });
});
