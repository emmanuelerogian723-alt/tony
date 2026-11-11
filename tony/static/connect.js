/* Tony · Google consent helper.
   Uses the Firebase project the deployment already signs users in with, so a
   provider account can be connected with one tap and no client secret. */
(function () {
  function cfg() { return window.TONY_FB || {}; }
  Object.defineProperty(window, 'TonyConnect', { configurable: true, writable: true, value: null });
  var FB = null;
  var AUTH = 'https://www.googleapis.com/auth/';
  function scopeUrl(s) {
    if (!s) return '';
    if (s.indexOf('http') === 0) return s;
    if (s === 'email') return AUTH + 'userinfo.email';
    if (s === 'profile') return AUTH + 'userinfo.profile';
    if (s === 'openid') return 'openid';
    return AUTH + s;
  }
  FB = null;
  function conf() { return cfg(); }
  function auth() {
    if (!conf().api_key) throw new Error('Google sign-in is not configured on this server.');
    if (!window.firebase || !window.firebase.auth) throw new Error('Google is still loading. Try again in a second.');
    if (!firebase.apps.length) {
      firebase.initializeApp({ apiKey: conf().api_key, authDomain: conf().auth_domain, projectId: conf().project_id });
    }
    return firebase.auth();
  }
  function provider(scopes) {
    var p = new firebase.auth.GoogleAuthProvider();
    (scopes || []).map(scopeUrl).filter(Boolean).forEach(function (s) { p.addScope(s); });
    p.setCustomParameters({ prompt: 'consent' });
    return p;
  }
  async function google(scopes, tag) {
    var a = auth();
    var p = provider(scopes);
    if (/Android|iPhone|iPad|Mobile/i.test(navigator.userAgent)) {
      sessionStorage.setItem('tony_g_pending', JSON.stringify({ tag: tag || '' }));
      await a.signInWithRedirect(p);
      return null;
    }
    var cred = await a.signInWithPopup(p);
    var token = cred && cred.credential && cred.credential.accessToken;
    if (!token) throw new Error('Google did not return an access token.');
    return token;
  }
  async function finishRedirect() {
    var pending = sessionStorage.getItem('tony_g_pending');
    if (!pending) return null;
    sessionStorage.removeItem('tony_g_pending');
    var res = await auth().getRedirectResult();
    var token = res && res.credential && res.credential.accessToken;
    return token || null;
  }
  window.TonyConnect = {
    google: google,
    finishRedirect: finishRedirect,
    get config() { return conf(); },
  };
})();
