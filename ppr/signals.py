# signals.py
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from .models import PPRYuborish, PPRTasdiqlash, Notification,ArizaYuborish, KelganArizalar,XaridAriza, XaridStep

User = get_user_model()



OY_NOMLARI = {
    1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel", 5: "May", 6: "Iyun",
    7: "Iyul", 8: "Avgust", 9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr"
}


@receiver(post_save, sender=PPRYuborish)
def notify_on_ppr_yuborish(sender, instance, created, **kwargs):
    
    if instance.status == 'yuborildi':
        # Faqat o'sha tarkibiy tuzilmadagi rahbarlarni (is_tarkibiy) topish
        rahbarlar = User.objects.filter(
            tarkibiy_tuzilma=instance.tarkibiy_tuzilma,
            role='tarkibiy' # User modelidagi rol nomi
        )
        oy_nomi = OY_NOMLARI.get(instance.oy, instance.oy)
        
        for rahbar in rahbarlar:
            Notification.objects.create(
                bolim_category=instance.bolim_category,
                tarkibiy_tuzilma=instance.tarkibiy_tuzilma,
                title="Yangi PPR paketi kelib tushdi",
                message=f"{instance.bolim_category.nomi} bo'limidan {instance.yil}-yil {oy_nomi} oyi uchun tasdiqlash so'rovi keldi.",
                link_id=instance.id,
                for_rahbar=True
            )

@receiver(post_save, sender=PPRTasdiqlash)
def notification_on_ppr_tasdiqlash(sender, instance, created, **kwargs):
    if created:
        paketi = instance.yuborish_paketi
        status_text = "tasdiqlandi" if instance.status == "tasdiqlandi" else "rad etildi"
        oy_nomi = OY_NOMLARI.get(paketi.oy, paketi.oy)

        # FAQAT BITTA XABAR YARATILADI
        Notification.objects.create(
            bolim_category=paketi.bolim_category,
            tarkibiy_tuzilma=paketi.tarkibiy_tuzilma,
            title=f"{paketi.bolim_category.nomi}: Paket {status_text}",
            message=f"{paketi.yil}-yil {oy_nomi} oyi uchun yuborilgan paket {status_text}.",
            link_id=paketi.id
        )
        
        
@receiver(m2m_changed, sender=ArizaYuborish.tuzilmalar.through)
def notify_on_ariza_yuborish(sender, instance, action, **kwargs):
    """
    Yangi ariza yaratilganda ijrochilarga xabar boradi.
    M2M changed ishlatish shart, chunki post_save da tuzilmalar hali birikmagan bo'ladi.
    """
    if action == "post_add":
        try:
            yuboruvchi = instance.created_by
            yuboruvchi_nomi = f"{yuboruvchi.first_name} {yuboruvchi.last_name}".strip() or yuboruvchi.username
            
            # Modelda 'nomi' yo'qligi uchun 'comment'ni ishlatamiz
            ariza_text = getattr(instance, 'comment', 'Yangi ariza')[:50]
            
            tuzilmalar = instance.tuzilmalar.all()
            for tuzilma in tuzilmalar:
                Notification.objects.get_or_create(
                    tarkibiy_tuzilma=tuzilma,
                    link_id=instance.id,
                    title="Yangi ariza kelib tushdi",
                    defaults={
                        'message': f"{yuboruvchi_nomi}dan yangi ariza: {ariza_text}...",
                        'for_rahbar': True
                    }
                )
        except Exception as e:
            print(f"Signal Error (ArizaYuborish): {e}")

@receiver(post_save, sender=KelganArizalar)
def notify_on_ariza_status_update(sender, instance, created, **kwargs):
    if created:
        try:
            ariza = instance.ariza
            yuboruvchi = ariza.created_by
            status_o_zgartirgan_user = instance.created_by

            status_map = {
                'jarayonda': "jarayonda",
                'bajarilmoqda': "bajarilmoqda",
                'rad_etildi': "rad etildi",
                'tasdiqlandi': "tasdiqlandi",
                'tasdiqlanmoqda': "tasdiqlanmoqda",
                'qaytarildi': "qaytarildi",
                'bajarilgan': "bajarilgan"
            }
            status_text = status_map.get(instance.status, instance.status)
            ariza_text = getattr(ariza, 'comment', f"#{ariza.id}")[:30]

            
            if status_o_zgartirgan_user != yuboruvchi:
                u_tarkibiy = getattr(yuboruvchi, 'tarkibiy_tuzilma', None)
                u_bolim_cat = None
                if hasattr(yuboruvchi, 'bolim_profile') and yuboruvchi.bolim_profile:
                    u_bolim_cat = yuboruvchi.bolim_profile.bolim_category

                Notification.objects.create(
                    bolim_category=u_bolim_cat,
                    tarkibiy_tuzilma=u_tarkibiy,
                    title="Ariza holati yangilandi",
                    message=f"Sizning '{ariza_text}' arizangiz statusi '{status_text}' bo'ldi.",
                    link_id=ariza.id,
                    for_rahbar=False
                )

            
            else:
                # Arizadagi barcha ijrochi tuzilmalarni olamiz
                tuzilmalar = ariza.tuzilmalar.all()
                for tuzilma in tuzilmalar:
                    Notification.objects.create(
                        tarkibiy_tuzilma=tuzilma,
                        title="Ariza yakunlandi",
                        message=f"Siz ijro qilgan '{ariza_text}' arizasi yuboruvchi tomonidan '{status_text}' holatiga o'tkazildi.",
                        link_id=ariza.id,
                        for_rahbar=True # Ijrochi tuzilma rahbarlari ko'rishi uchun
                    )

        except Exception as e:
            import traceback
            print(f"!!! Notification Error Traceback: {traceback.format_exc()}")
            
            
            
            
#3 chi bu xarid uchun notiflar
@receiver(m2m_changed, sender=XaridAriza.tuzilmalar.through)
def notify_on_xarid_yuborish(sender, instance, action, **kwargs):
    if action == "post_add":
        try:
            yuboruvchi = instance.created_by
            # Tuzilma nomini olish (foydalanuvchi profilidan)
            kimdan = getattr(yuboruvchi, 'tarkibiy_tuzilma', None)
            kimdan_nomi = kimdan.tuzilma_nomi if kimdan else yuboruvchi.username
            
            ariza_qisqacha = instance.comment[:50]
            
            tuzilmalar = instance.tuzilmalar.all()
            for tuzilma in tuzilmalar:
                Notification.objects.create(
                    tarkibiy_tuzilma=tuzilma,
                    title="Xarid uchun yangi ariza",
                    message=f"{kimdan_nomi}dan kelishish uchun xarid arizasi keldi: {ariza_qisqacha}",
                    link_id=instance.id,
                    for_rahbar=True
                )
        except Exception as e:
            print(f"Xarid Signal Error (Yuborish): {e}")

# 2. XaridStep (Qarorlar) va XaridAriza statusi o'zgarganda xabar yuborish
@receiver(post_save, sender=XaridAriza)
def notify_on_xarid_status_change(sender, instance, created, **kwargs):
    # Bu signal faqat status o'zgarganda (update bo'lganda) ishlaydi
    if not created:
        try:
            muallif = instance.created_by
            muallif_tuzilma = getattr(muallif, 'tarkibiy_tuzilma', None)
            
            # A) Agar ariza RAD ETILSA (XaridStep orqali yoki Monitoring orqali)
            if instance.status == 'rad_etildi':
                Notification.objects.create(
                    tarkibiy_tuzilma=muallif_tuzilma,
                    title="Xarid arizasi rad etildi",
                    message=f"Sizning #{instance.id} xarid arizangiz rad etildi.",
                    link_id=instance.id,
                    for_rahbar=True
                )
            
            # B) Agar barcha tuzilmalar kelishib bo'lsa -> Monitoring xodimlariga (Tasdiqlash uchun)
            elif instance.status == 'kelishildi':
              
                Notification.objects.create(
                    title="Tasdiqlash uchun yangi xarid",
                    message=f"#{instance.id} xarid arizasi barcha tuzilmalar bilan kelishildi. Tasdiqlash kutilmoqda.",
                    link_id=instance.id,
                    for_rahbar=True # Monitoring xodimlari ko'rishi uchun
                )

            # C) Agar Monitoring TASDIQLASA
            elif instance.status == 'tasdiqlandi':
                Notification.objects.create(
                    tarkibiy_tuzilma=muallif_tuzilma,
                    title="Xarid arizasi tasdiqlandi",
                    message=f"Tabriklaymiz! Sizning #{instance.id} xarid arizangiz to'liq tasdiqlandi.",
                    link_id=instance.id,
                    for_rahbar=True
                )
                
        except Exception as e:
            print(f"Xarid Signal Error (Status): {e}")