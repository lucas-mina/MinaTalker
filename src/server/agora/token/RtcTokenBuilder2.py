# -*- coding: utf-8 -*-
# Vendored from AgoraIO/Tools (AccessToken2). Apache-2.0.
from .AccessToken2 import AccessToken, ServiceRtc, ServiceRtm

Role_Publisher = 1
Role_Subscriber = 2


class RtcTokenBuilder:
    @staticmethod
    def build_token_with_uid(
        app_id,
        app_certificate,
        channel_name,
        uid,
        role,
        token_expire,
        privilege_expire=0,
    ):
        return RtcTokenBuilder.build_token_with_user_account(
            app_id,
            app_certificate,
            channel_name,
            uid,
            role,
            token_expire,
            privilege_expire,
        )

    @staticmethod
    def build_token_with_user_account(
        app_id,
        app_certificate,
        channel_name,
        account,
        role,
        token_expire,
        privilege_expire=0,
    ):
        token = AccessToken(app_id, app_certificate, expire=token_expire)

        service_rtc = ServiceRtc(channel_name, account)
        service_rtc.add_privilege(ServiceRtc.kPrivilegeJoinChannel, privilege_expire)
        if role == Role_Publisher:
            service_rtc.add_privilege(ServiceRtc.kPrivilegePublishAudioStream, privilege_expire)
            service_rtc.add_privilege(ServiceRtc.kPrivilegePublishVideoStream, privilege_expire)
            service_rtc.add_privilege(ServiceRtc.kPrivilegePublishDataStream, privilege_expire)
        token.add_service(service_rtc)

        return token.build()
