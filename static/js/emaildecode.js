var emails = document.getElementsByClassName("email");

for (var i = 0; i < emails.length; i++) {
  var b64 = emails[i].innerHTML;
  var decoded = window.atob(b64);
  emails[i].innerHTML = decoded;
  emails[i].href = "mailto:" + decoded;
}
