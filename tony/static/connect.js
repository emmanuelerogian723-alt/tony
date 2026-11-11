/* Tony · Google consent helper.
   Uses the Firebase project the deployment already signs users in with, so a
   provider account can be connected with one tap and no client secret. */
(function () {
  var FB = window.TONY_FB || {};
  var AUTH = 'https://www.googleapis.com/auth/';
  function scopeUrl(s) {
    if (!s) return '';
    if (s.indexOf('http') === 0) return s;
    if (s === 'email') return AUTH + 'userinfo.email';
    if (s === 'profile') return AUTH + 'userinfo.profile';
    if (s === 'openid') return 'openid';
    return AUTH + s;
  }
  function auth() {
    if (!FB.api_key) throw new Error('Google sign-in is not configured on this server.');
    if (!window.firebase || !window.firebase.auth) throw new Error('Google is still loading. Try again in a second.');
    if (!firebase.apps.length) {
      firebase.initializeApp({ apiKey: FB.api_key, authDomain: FB.auth_domain, projectId: FB.project_id });
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
  window.TonyConnect = { google: google, finishRedirect: finishRedirect, config: FB };
})();
