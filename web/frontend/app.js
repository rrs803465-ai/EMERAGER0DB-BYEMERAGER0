// Fills in the latest released version from the release API. Fails quietly if the API is unavailable.
(function () {
  var target = document.getElementById("latest-version");
  if (!target) return;
  fetch("/api/version", { headers: { Accept: "application/json" } })
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (data) {
      target.textContent = data.latest;
    })
    .catch(function () {
      target.textContent = "unavailable";
    });
})();
