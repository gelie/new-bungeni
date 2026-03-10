from decouple import config
from exchangelib import (
    DELEGATE,
    Account,
    BaseProtocol,
    Configuration,
    Credentials,
    HTMLBody,
    Message,
    NoVerifyHTTPAdapter,
)

BaseProtocol.HTTP_ADAPTER_CLS = NoVerifyHTTPAdapter


class EWSMail(object):
    def __init__(self):
        self.credentials = Credentials(
            username=config("EMAIL_HOST_USER"), password=config("EMAIL_HOST_PASSWORD")
        )
        self.config = Configuration(
            server=config("EMAIL_HOST"), credentials=self.credentials
        )
        self.account = Account(
            primary_smtp_address=config("MY_EMAIL_ADDRESS"),
            credentials=self.credentials,
            config=self.config,
            autodiscover=False,
            access_type=DELEGATE,
        )

    def send(self, subject: str, body: str, recipients: list):
        m = Message(
            account=self.account,
            folder=self.account.sent,
            author=config("DEFAULT_FROM_EMAIL"),
            subject=subject,
            body=HTMLBody(body),
            to_recipients=recipients,
        )
        m.send_and_save()
