/**
 * FIGE (2026-08-31) - logique de localisation client. Couvert par
 * tests/test_app.py. Modifier avec prudence (le flux d'entree en depend).
 *
 * FixPro - localisation client automatique.
 *
 *  - request()      : declenche la demande de position (bouton "Autoriser").
 *  - setZone(name)  : enregistre un quartier choisi a la main.
 *  - autoResume()   : sur chaque page, si l'autorisation a deja ete accordee
 *                     et qu'aucune position n'est en session, recupere la
 *                     position en silence (sans popup) puis recharge une fois.
 *
 * Le popup natif du navigateur n'apparait qu'a la premiere demande : ensuite
 * navigator.permissions renvoie "granted" et tout se fait sans interaction.
 */
(function (global) {
  "use strict";

  function csrf() {
    var m = document.querySelector('meta[name="csrf-token"]');
    return m ? m.content : "";
  }

  function post(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      credentials: "same-origin",
      body: JSON.stringify(payload || {}),
    }).then(function (r) { return r.json().catch(function () { return {}; }); });
  }

  function go(next) {
    window.location.assign(next || "/artisans");
  }

  var FixProGeo = {
    /** Bouton "Autoriser ma position". */
    request: function (opts) {
      opts = opts || {};
      var next = opts.next || "/artisans";
      if (!navigator.geolocation) {
        if (opts.onUnsupported) opts.onUnsupported();
        return;
      }
      if (opts.onStart) opts.onStart();
      navigator.geolocation.getCurrentPosition(
        function (pos) {
          post("/api/location", {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            accuracy: pos.coords.accuracy || 0,
          }).then(function (d) {
            if (d && d.ok) { go(next); }
            else if (opts.onError) { opts.onError(d && d.error); }
          }).catch(function () { if (opts.onError) opts.onError(); });
        },
        function (err) {
          post("/api/location/denied", {}).catch(function () {});
          if (opts.onDenied) opts.onDenied(err);
        },
        { enableHighAccuracy: true, timeout: 12000, maximumAge: 300000 }
      );
    },

    /** Quartier choisi manuellement dans la liste. */
    setZone: function (name, opts) {
      opts = opts || {};
      var next = opts.next || "/artisans";
      post("/api/location/zone", { zone: name }).then(function (d) {
        if (d && d.ok) { go(next); }
        else if (opts.onError) { opts.onError(d && d.error); }
      }).catch(function () { if (opts.onError) opts.onError(); });
    },

    /** Reprise silencieuse sur les visites suivantes (aucun popup). */
    autoResume: function () {
      try {
        if (sessionStorage.getItem("fixpro_geo_session")) return;
      } catch (e) { /* sessionStorage indisponible : on continue */ }

      if (!navigator.permissions || !navigator.geolocation) return;

      navigator.permissions.query({ name: "geolocation" }).then(function (status) {
        if (status.state !== "granted") return;
        navigator.geolocation.getCurrentPosition(function (pos) {
          post("/api/location", {
            lat: pos.coords.latitude,
            lon: pos.coords.longitude,
            accuracy: pos.coords.accuracy || 0,
          }).then(function (d) {
            try { sessionStorage.setItem("fixpro_geo_session", "1"); } catch (e) {}
            if (d && d.ok) { window.location.reload(); }
          }).catch(function () {});
        }, function () {}, { timeout: 10000, maximumAge: 600000 });
      }).catch(function () {});
    },
  };

  global.FixProGeo = FixProGeo;

  document.addEventListener("DOMContentLoaded", function () {
    // Reprise silencieuse partout, SAUF sur l'ecran de localisation lui-meme.
    if (!document.body || !document.body.hasAttribute("data-location-gate")) {
      FixProGeo.autoResume();
    }
  });
})(window);
