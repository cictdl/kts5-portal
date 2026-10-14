// The stage screen of the launch of the registration portal (1.2.69): the button, or Enter, Space or a presenter's clicker,
// opens the curtain, lets petals in the colours of the flag fall, shows the address and its QR code, and then opens the home
// page as launched (unless the address has ?stay=1). Nothing on the portal changes with it.
(function () {
  "use strict";
  var stage = document.getElementById("stage"), go = document.getElementById("go"), full = document.getElementById("full");
  var done = false;
  var calm = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function petals() {
    if (calm) return;
    var colours = ["#FF9933", "#FFFFFF", "#138808", "#F2C46B"];
    for (var i = 0; i < 140; i++) {
      var p = document.createElement("span");
      p.className = "petal";
      p.style.left = (Math.random() * 100) + "vw";
      p.style.background = colours[i % colours.length];
      p.style.animationDuration = (4 + Math.random() * 4) + "s";
      p.style.animationDelay = (Math.random() * 2.2) + "s";
      p.style.setProperty("--dx", ((Math.random() - 0.5) * 30) + "vw");
      p.style.setProperty("--rot", (Math.random() * 900 - 450) + "deg");
      document.body.appendChild(p);
    }
  }

  function launch() {
    if (done) return;
    done = true;
    stage.classList.add("open");
    petals();
    if (!stage.dataset.stay) {
      setTimeout(function () { window.location.href = stage.dataset.home; }, calm ? 5000 : 9000);
    }
  }

  go.addEventListener("click", launch);
  document.addEventListener("keydown", function (e) {
    if (["Enter", " ", "PageDown", "ArrowRight", "ArrowDown"].indexOf(e.key) >= 0 && !done) {
      e.preventDefault();
      launch();
    }
  });
  if (full) {
    full.addEventListener("click", function () {
      var el = document.documentElement;
      if (el.requestFullscreen) el.requestFullscreen();
    });
  }
  go.focus();
})();
