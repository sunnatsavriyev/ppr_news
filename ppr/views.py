from collections import defaultdict
from rest_framework import viewsets,filters,mixins

from ppr.permissions import IsMonitoringReadOnly
from .models import *
from .serializers import *
from rest_framework import permissions, status
from rest_framework.response import Response
from django.db.models import Prefetch
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import MultiPartParser, FormParser
from .pagination import CustomPagination
from django_filters.rest_framework import DjangoFilterBackend
import django_filters
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from datetime import date, timedelta
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models import Q
from django.utils import timezone
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.db.models.functions import TruncDate
from django.db.models import Count
from django.contrib.contenttypes.models import ContentType
from django_filters import rest_framework as filters
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.types import OpenApiTypes
from django.db.models.functions import ExtractMonth, ExtractYear
from django.db.models.functions import Abs 
from datetime import datetime



class UserTuzilmaViewSet(viewsets.ModelViewSet):
    serializer_class = UserTuzilmaSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    pagination_class = CustomPagination
    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]
    search_fields = [
        "username",
        "email",
        "passport_seriya",
        "role",
        "tarkibiy_tuzilma__tuzilma_nomi",
        "bekat_nomi__bekat_nomi",
    ]
    filterset_fields = {
        "role": ["exact"],
        "tarkibiy_tuzilma": ["exact"],
        "bekat_nomi": ["exact"],
        "is_active": ["exact"],
    }
    ordering_fields = ["id", "username", "date_joined"]
    ordering = ["-id"]

    def get_queryset(self):
        user = self.request.user

        # ADMIN, SUPERUSER, MONITORING → hammani ko‘radi
        if user.is_superuser or user.role in ["admin", "monitoring"]:
            return CustomUser.objects.all().order_by('-id')
        
        
        if user.role == "tarkibiy":
            return CustomUser.objects.filter(
                Q(id=user.id) |                    
                Q(tarkibiy_tuzilma=user.tarkibiy_tuzilma)
            )

        return CustomUser.objects.filter(id=user.id)

    # CREATE – faqat admin/superuser
    def perform_create(self, serializer):
        user = self.request.user
        if not (user.is_superuser or user.is_admin()):
            raise PermissionDenied("Faqat admin foydalanuvchi yaratishi mumkin.")
        serializer.save()

    
    
    def get_permissions(self):
        user = self.request.user

        # Agar foydalanuvchi monitoring bo'lsa
        if user.is_authenticated and user.role == "monitoring":
            # Yaratish (POST) qat'iy taqiqlanadi
            if self.request.method == 'POST':
                raise PermissionDenied("Monitoring xodimi yangi foydalanuvchi qo'sholmaydi.")
            
            return super().get_permissions()
        
        # Admin va boshqalar uchun standart holat
        return super().get_permissions()
    
    
    
    # ---------------- UPDATE ----------------
    def perform_update(self, serializer):
        user = self.request.user
        obj = self.get_object()

        # ADMIN yoki SUPERADMIN → barchani o‘zgartira oladi
        if user.is_superuser or user.is_admin():
            serializer.save()
            return

        # Oddiy user → faqat o‘zini update qila oladi
        if user.id != obj.id:
            raise PermissionDenied("Siz faqat o‘zingizni o‘zgartira olasiz.")

        serializer.save()

    # ---------------- DELETE ----------------
    def perform_destroy(self, instance):
        user = self.request.user

        # Faqat admin / superuser
        if not (user.is_superuser or user.is_admin()):
            raise PermissionDenied("Faqat admin foydalanuvchi o‘chirishi mumkin.")

        # -------- 24 SOATLIK CHEK --------
        created_time = instance.date_joined
        now = timezone.now()

        if now - created_time > timedelta(hours=24):
            raise PermissionDenied(
                "Bu foydalanuvchini o‘chirish mumkin emas. "
                "Foydalanuvchi yaratilganidan 24 soat o‘tgan."
            )

        instance.delete()



class BolimCategoryViewSet(viewsets.ModelViewSet):
    serializer_class = BolimCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        
        # Admin hammasini ko'radi
        if user.is_superuser or user.role in ['admin', 'monitoring']:
            return BolimCategory.objects.all().order_by('id')
        
        # Tuzilma rahbari faqat o'ziga tegishli nomlarni ko'radi
        if user.role == 'tarkibiy' and user.tarkibiy_tuzilma:
            return BolimCategory.objects.filter(tuzilma=user.tarkibiy_tuzilma).order_by("id")
            
        return BolimCategory.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        
        if user.role != 'tarkibiy' and not user.is_superuser:
            raise PermissionDenied("Faqat tuzilma rahbari bo'lim nomini yarata oladi.")
            
        if user.role == 'tarkibiy':
            # Avtomatik ravishda userning tuzilmasini biriktiramiz
            serializer.save(
                tuzilma=user.tarkibiy_tuzilma,
                created_by=user
            )
        else:
            serializer.save(created_by=user)




class BolimViewSet(viewsets.ModelViewSet):
    serializer_class = BolimUserSerializer
    permission_classes = [permissions.IsAuthenticated] 

    def get_queryset(self):
        user = self.request.user

        # ADMIN / SUPERUSER / MONITORING → hammasi
        if user.is_superuser or user.role in ["admin", "monitoring"]:
            return Bolim.objects.all().order_by('-id')

        if user.role == "tarkibiy":
            return Bolim.objects.filter(tuzilma=user.tarkibiy_tuzilma)

        if user.role == "bolim":
            return Bolim.objects.filter(user=user)

        return Bolim.objects.none()  
        
    def get_permissions(self):
        user = self.request.user

        if user.role == "monitoring":
            if self.request.method not in permissions.SAFE_METHODS:
                raise PermissionDenied("Monitoring faqat ko‘rishi mumkin")

        return super().get_permissions()
    

class MeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserTuzilmaSerializer(
            request.user,
            context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)





class TuzilmaNomiViewSet(viewsets.ModelViewSet):
    queryset = TarkibiyTuzilma.objects.filter(status=True)
    serializer_class = TuzilmaSerializers

    def get_queryset(self):
        return TarkibiyTuzilma.objects.filter(status=True)




class ArizaYuborishFilter(django_filters.FilterSet):
    # Tuzilma bo‘yicha filter (ID orqali)
    tuzilma = django_filters.NumberFilter(field_name='tuzilmalar__id')

    # Kim tomonidan (ID orqali)
    kim_tomonidan = django_filters.NumberFilter(field_name='kim_tomonidan_id')

    # Created by (ID orqali)
    created_by = django_filters.NumberFilter(field_name='created_by_id')
    turi = django_filters.CharFilter(lookup_expr='exact')
    # Tuzilma nomi orqali filter (TEXT)
    tuzilma_nomi = django_filters.CharFilter(
        field_name='tuzilmalar__tuzilma_nomi',
        lookup_expr='icontains'
    )
    status = django_filters.CharFilter(lookup_expr='exact')

    class Meta:
        model = ArizaYuborish
        fields = [
            'status',
            'is_approved',
            'tuzilma',
            'kim_tomonidan',
            'created_by',
            'turi',
            'tuzilma_nomi',
            'status',
        ]





class ArizaYuborishViewSet(viewsets.ModelViewSet):
    queryset = ArizaYuborish.objects.all().order_by('-id')
    serializer_class = ArizaYuborishSerializer
    permission_classes = [permissions.IsAuthenticated, IsMonitoringReadOnly]
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]

    search_fields = ['status', 'tuzilmalar__tuzilma_nomi', 'created_by__username', 'comment']
    ordering_fields = ['id', 'tuzilmalar__tuzilma_nomi', 'created_by__username']
    # filterset_fields = ['status', 'is_approved']
    filterset_class = ArizaYuborishFilter

    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_admin() or user.is_monitoring():
            return ArizaYuborish.objects.all().order_by('-id')

        user_tuzilma = getattr(user, 'tarkibiy_tuzilma', None)
        if not user_tuzilma and user.bolim:
            user_tuzilma = getattr(user.bolim, 'tarkibiy_tuzilma', None)

        query = models.Q(created_by=user)

        if user.is_bolim() and user.bolim:
            query |= models.Q(created_by__bolim=user.bolim)
            
        if user_tuzilma:
            query |= models.Q(created_by__tarkibiy_tuzilma=user_tuzilma)

        return ArizaYuborish.objects.filter(query).distinct().order_by('-id')



    
    
    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(
            status="jarayonda",
            is_approved=user.is_superuser
        )



class KelganArizalarFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(lookup_expr='exact')
    is_approved = django_filters.BooleanFilter()

    tuzilma_nomi = django_filters.CharFilter(
        field_name='ariza__tuzilma__tuzilma_nomi',
        lookup_expr='icontains'
    )
    turi = django_filters.CharFilter(lookup_expr='exact')
    created_by = django_filters.NumberFilter(
        field_name='ariza__created_by_id'
    )

    class Meta:
        model = KelganArizalar
        fields = ['status', 'is_approved', 'tuzilma_nomi', 'turi', 'created_by']


            
   
class KelganArizalarViewSet(viewsets.ModelViewSet):
    queryset = ArizaYuborish.objects.all().order_by('-id')
    serializer_class = ArizaYuborishWithKelganSerializer
    permission_classes = [permissions.IsAuthenticated, IsMonitoringReadOnly]

    search_fields = [
        'status',
        'tuzilmalar__tuzilma_nomi',
        'comment',
        'created_by__username',
        'kelganlar__comment',
        'kelganlar__status'
    ]

    ordering_fields = ['id', 'sana', 'status']

    filterset_class = ArizaYuborishFilter   

    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or user.is_admin() or user.is_monitoring():
            return ArizaYuborish.objects.prefetch_related(
                Prefetch('kelganlar', queryset=KelganArizalar.objects.all())
            ).order_by('-id')

        # Tuzilmani aniqlash
        user_tuzilma = getattr(user, 'tarkibiy_tuzilma', None)
        if not user_tuzilma and user.bolim:
            user_tuzilma = getattr(user.bolim, 'tarkibiy_tuzilma', None)

        if user_tuzilma:
            # 1. Faqat mening tuzilmamga yuborilgan (Kelgan) arizalar
            query = models.Q(tuzilmalar=user_tuzilma)
            
            # 2. Lekin o'zimiz (bizning tuzilma xodimlari) yuborganlarni CHIQARIB TASHLASH
            # Shunda 70-id kabi arizalar bu ro'yxatdan yo'qoladi
            return ArizaYuborish.objects.filter(query).exclude(
                created_by__tarkibiy_tuzilma=user_tuzilma
            ).prefetch_related(
                Prefetch('kelganlar', queryset=KelganArizalar.objects.all()),
                'rasmlar', 'tuzilmalar'
            ).distinct().order_by('-id')

        return ArizaYuborish.objects.none()

    
    
    
class ArizaStatusViewSet(viewsets.ModelViewSet):
    queryset = ArizaYuborish.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = ArizaStatusUpdateSerializer

    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ariza = serializer.validated_data['ariza']
        holat = serializer.validated_data['holat']
        comment = serializer.validated_data.get('comment', '')
        akt_file = serializer.validated_data.get('akt_file')
        ilovalar = serializer.validated_data.get('ilovalar')
        photo = serializer.validated_data.get('photos', [])
        user = request.user
        
        # 1. Foydalanuvchi huquqlarini tekshirish
        is_creator = (ariza.created_by == user)
        
        # Foydalanuvchi tuzilmasini aniqlash
        user_tuzilma = getattr(user, 'tarkibiy_tuzilma', None) or \
                       getattr(user, 'bekat_nomi', None) or \
                       getattr(user, 'bolim', None)
        
        # Qabul qiluvchi (ijrochi) tomonmi?
        is_receiver = ariza.tuzilmalar.filter(id=user_tuzilma.id).exists() if user_tuzilma else False
        is_admin = user.is_superuser or getattr(user, "role", None) == "admin"

        # 2. Ruxsat etilgan statuslar
        ALLOWED_FOR_CREATOR = ['rad_etildi', 'bajarilgan']
        ALLOWED_FOR_RECEIVER = ['qaytarildi', 'bajarilmoqda', 'tasdiqlanmoqda']

        # 3. Mantiqiy cheklovlar va Xatolik xabarlari
        if is_admin:
            # Admin har qanday statusni o'rnata oladi
            pass
            
        elif is_creator and not is_receiver:
            # Faqat yuborgan odam bo'lsa
            if holat not in ALLOWED_FOR_CREATOR:
                return Response({
                    "status": "error",
                    "message": "Sizda ushbu amalni bajarish huquqi yo'q.",
                    "detail": f"Ariza yuboruvchisi sifatida siz faqat statusni {', '.join(ALLOWED_FOR_CREATOR)} qila olasiz.",
                    "current_user_role": "Yuboruvchi"
                }, status=status.HTTP_400_BAD_REQUEST)
                
        elif is_receiver:
            # Qabul qilgan (ijrochi) tomon bo'lsa
            if holat not in ALLOWED_FOR_RECEIVER:
                return Response({
                    "status": "error",
                    "message": "Noto'g'ri status tanlandi.",
                    "detail": f"Ijrochi sifatida siz faqat statusni {', '.join(ALLOWED_FOR_RECEIVER)} qila olasiz.",
                    "current_user_role": "Ijrochi"
                }, status=status.HTTP_400_BAD_REQUEST)
        
        else:
            # Ariza bilan hech qanday aloqasi bo'lmasa
            return Response({
                "status": "error",
                "message": "Ruxsat etilmadi.",
                "detail": "Siz ushbu arizaning yuboruvchisi ham, ijrochisi ham emassiz."
            }, status=status.HTTP_403_FORBIDDEN)

        # 4. Saqlash jarayoni
        try:
            # Asosiy arizani yangilash
            ariza.status = holat
            ariza.save()

            # Tarix uchun KelganArizalar (Step) yaratish
            step_obj = KelganArizalar.objects.create(
                ariza=ariza,
                created_by=user,
                comment=comment,
                status=holat,
                is_approved=user.is_superuser,
                akt_file=akt_file,
                ilovalar=ilovalar
            )
            if photo:
                for img in photo:
                    KelganArizaImage.objects.create(
                        step=step_obj, 
                        rasm=img
                    )
                    
            return Response({
                "status": "success",
                "message": f"Ariza holati '{holat}' ga o'zgartirildi.",
                "data": {
                    "ariza_id": ariza.id,
                    "new_status": holat
                }
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({
                "status": "error",
                "message": "Tizimda xatolik yuz berdi.",
                "detail": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class KelganArizalarCreateViewSet(viewsets.ModelViewSet):
    queryset = KelganArizalar.objects.all()
    serializer_class = KelganArizalarSerializer
    permission_classes = [permissions.IsAuthenticated,IsMonitoringReadOnly]
    search_fields = ['status', 'ariza__tuzilma__tuzilma_nomi', 'created_by__username']
    ordering_fields = ['id', 'sana', 'status']
    filterset_fields = ['status', 'is_approved' ]
    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user
        qs = KelganArizalar.objects.all()
        
        if user.is_superuser or getattr(user, 'role', None) == "admin":
            return qs
        elif user.tarkibiy_tuzilma:
            return qs.filter(ariza__tuzilma=user.tarkibiy_tuzilma)
        elif user.bekat_nomi:
            tuzilma = TarkibiyTuzilma.objects.filter(tuzilma_nomi=user.bekat_nomi.bekat_nomi).first()
            if tuzilma:
                return qs.filter(ariza__tuzilma=tuzilma)
        return qs.none()

    def get_serializer(self, *args, **kwargs):
        serializer_class = self.get_serializer_class()
        kwargs['context'] = self.get_serializer_context()
        serializer = serializer_class(*args, **kwargs)

        # Faqat hali bajarilmagan arizalarni dropdownga chiqaramiz
        user = self.request.user
        ariza_qs = ArizaYuborish.objects.exclude(status="bajarilgan")

        if not user.is_superuser:
            if user.tarkibiy_tuzilma:
                ariza_qs = ariza_qs.filter(tuzilma=user.tarkibiy_tuzilma)
            elif user.bekat_nomi:
                tuzilma = TarkibiyTuzilma.objects.filter(
                    tuzilma_nomi=user.bekat_nomi.bekat_nomi
                ).first()
                if tuzilma:
                    ariza_qs = ariza_qs.filter(tuzilma=tuzilma)
                else:
                    ariza_qs = ArizaYuborish.objects.none()

        # Agar serializer many=True bo'lsa, child.fields ishlatish
        if hasattr(serializer, 'child'):
            serializer.child.fields['ariza'].queryset = ariza_qs
        else:
            serializer.fields['ariza'].queryset = ariza_qs

        return serializer




    def perform_create(self, serializer):
        user = self.request.user
        kelgan = serializer.save(
            created_by=user,
            is_approved=user.is_superuser
        )
        # Javob qo‘shilganda asosiy arizani statusini "bajarildi" ga o‘zgartirish
        ariza = kelgan.ariza
        ariza.status = "bajarilgan"
        ariza.save()




class ArizaImageDeleteAPIView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        image = get_object_or_404(ArizaYuborishImage, pk=pk)

        if image.ariza.created_by != request.user and not request.user.is_superuser:
            return Response(
                {"detail": "Ruxsat yo'q"},
                status=status.HTTP_403_FORBIDDEN
            )

        image.rasm.delete(save=False)
        image.delete()

        return Response(
            {"detail": "Rasm o‘chirildi"},
            status=status.HTTP_204_NO_CONTENT
        )



class StepDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    # Swagger uchun request body
    step_ids_param = openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['step_ids'],
        properties={
            'step_ids': openapi.Schema(
                type=openapi.TYPE_ARRAY,
                items=openapi.Items(type=openapi.TYPE_INTEGER),
                description='O‘chiriladigan step IDlar ro‘yxati'
            )
        }
    )

    @swagger_auto_schema(
        request_body=step_ids_param,
        responses={
            200: openapi.Response(
                description="Steps deleted successfully",
                examples={
                    "application/json": {
                        "success": True,
                        "deleted_count": 3
                    }
                }
            ),
            400: "Step ID lar berilmagan",
            403: "Ruxsat yo‘q"
        }
    )
    def post(self, request):
        user = request.user
        # faqat admin va superuser
        if not (user.is_superuser or getattr(user, 'role', None) == 'admin'):
            return Response({"detail": "Ruxsat yo‘q"}, status=status.HTTP_403_FORBIDDEN)

        # step_ids olish
        step_ids = request.data.get("step_ids", [])
        if not step_ids or not isinstance(step_ids, list):
            return Response({"detail": "Step ID lar berilmagan"}, status=status.HTTP_400_BAD_REQUEST)

        # Steplarni filter qilish va o'chirish
        steps = KelganArizalar.objects.filter(id__in=step_ids)
        deleted_count = steps.count()
        steps.delete()

        return Response({
            "success": True,
            "deleted_count": deleted_count
        }, status=status.HTTP_200_OK)


# class KelganArizalarImagedeleteAPIView(APIView):
#     permission_classes = [permissions.IsAuthenticated]

#     def delete(self, request, pk):
#         image = get_object_or_404(KelganArizalarImage, pk=pk)

#         if image.kelgan_ariza.created_by != request.user and not request.user.is_superuser:
#             return Response(
#                 {"detail": "Ruxsat yo'q"},
#                 status=status.HTTP_403_FORBIDDEN
#             )

#         image.rasm.delete(save=False)
#         image.delete()

#         return Response(
#             {"detail": "Rasm o‘chirildi"},
#             status=status.HTTP_204_NO_CONTENT
#         )









def get_custom_queryset(viewset_instance):
    user = viewset_instance.request.user
    model = viewset_instance.queryset.model
    qs = model.objects.all().order_by('-id')

    # 1. Admin va Monitoring hamma narsani ko'radi
    if user.is_superuser or user.is_admin() or user.is_monitoring():
        return qs

    # 2. Tarkibiy (Tuzilma)
    if user.is_tarkibiy() and user.tarkibiy_tuzilma:
        return qs.filter(tarkibiy_tuzilma=user.tarkibiy_tuzilma)

    # 3. Bo'lim mantiqi
    if user.is_bolim():
        category = None
        if hasattr(user, 'bolim_profile') and user.bolim_profile.bolim_category:
            category = user.bolim_profile.bolim_category

        # PPRTuri modelida 'user', ObyektNomi modelida 'created_by'
        if hasattr(model, 'user'):
            query = Q(user=user)
        elif hasattr(model, 'created_by'):
            query = Q(created_by=user)
        else:
            query = Q(pk__isnull=True)  # Hech qaysi user bilan bog'lanmagan model

        # Shu bo'limdagi boshqa userlar qo'shgan obyektlar
        if category:
            query |= Q(user__bolim_profile__bolim_category=category) if hasattr(model, 'user') else Q(created_by__bolim_profile__bolim_category=category)

        return qs.filter(query).distinct()

    # 4. Bekat
    if user.is_bekat() and user.bekat_nomi:
        return qs.filter(bekat=user.bekat_nomi)

    # 5. Default: faqat o'zi qo'shgan
    if hasattr(model, 'user'):
        return qs.filter(user=user)
    elif hasattr(model, 'created_by'):
        return qs.filter(created_by=user)

    return qs.none()




            
class PPRTuriViewSet(viewsets.ModelViewSet):
    queryset = PPRTuri.objects.all().order_by('-id')
    serializer_class = PPRTuriSerializer
    permission_classes = [permissions.IsAuthenticated, IsMonitoringReadOnly]
    
    def get_queryset(self):
        return get_custom_queryset(self)

    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(
            user=user,
            tarkibiy_tuzilma=user.tarkibiy_tuzilma,
            bekat=user.bekat_nomi,
            bolim=user.bolim
        )
    


class ObyektNomiViewSet(viewsets.ModelViewSet):
    queryset = ObyektNomi.objects.all().order_by('-id')
    serializer_class = ObyektNomiSerializer
    pagination_class = CustomPagination
    search_fields = ['obyekt_nomi']
    filter_backends = [SearchFilter]
    permission_classes = [permissions.IsAuthenticated, IsMonitoringReadOnly]
    
    
    
    def get_queryset(self):
        return get_custom_queryset(self)

    def perform_create(self, serializer):
        user = self.request.user
        
        # 1. Userning bo'lim profilidan kategoriyani olamiz
        user_profile = getattr(user, 'bolim_profile', None)
        if not user_profile or not user_profile.bolim_category:
            raise ValidationError("Sizda bo'lim kategoriyasi aniqlanmagan.")

        user_category = user_profile.bolim_category
        obyekt_nomi = serializer.validated_data.get('obyekt_nomi')

        # 2. Tekshirish
        exists = ObyektNomi.objects.filter(
            obyekt_nomi=obyekt_nomi,
            tarkibiy_tuzilma=user.tarkibiy_tuzilma,
            bekat=user.bekat_nomi,
            bolim_category=user_category
        ).exists()

        if exists:
            raise ValidationError({
                "obyekt_nomi": f"'{user_category.nomi}' bo'limida ushbu nomli obyekt allaqachon mavjud."
            })

        # 3. Saqlash
        serializer.save(
            created_by=user,
            tarkibiy_tuzilma=user.tarkibiy_tuzilma,
            bekat=user.bekat_nomi,
            bolim_category=user_category
        )



class ObyektLocationViewSet(viewsets.ModelViewSet):
    queryset = ObyektLocation.objects.all().order_by('-id')
    serializer_class = ObyektLocationSerializer
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAuthenticated, IsMonitoringReadOnly]

    def get_queryset(self):
        return get_custom_queryset(self)


    def create(self, request, *args, **kwargs):
        user = request.user
        if user.is_monitoring():
            raise PermissionDenied("Monitoring faqat ko‘rishi mumkin")

        obyekt_id = request.data.get('obyekt')
        if not obyekt_id:
            return Response({"detail": "obyekt majburiy"}, status=400)

        if ObyektLocation.objects.filter(obyekt_id=obyekt_id).exists():
            return Response({"detail": "Bu obyekt uchun locatsiya allaqachon mavjud"}, status=400)

        return super().create(request, *args, **kwargs)






class PPRJadvalFilter(filters.FilterSet):
    tuzilma = filters.NumberFilter(field_name="tarkibiy_tuzilma_id")

    bolim_category = filters.CharFilter(
        field_name="bolim_category__nomi",
        lookup_expr="iexact"
    )

    ppr_turi = filters.CharFilter(
        field_name="ppr_turi__nomi",
        lookup_expr="iexact"
    )

    sana = filters.DateFromToRangeFilter()

    class Meta:
        model = PPRJadval
        fields = ["tuzilma", "bolim_category", "ppr_turi", "sana"]






class PPRYuborishViewSet(viewsets.ModelViewSet):
    queryset = PPRYuborish.objects.all()
    serializer_class = PPRYuborishSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        # Faqat faqat aktiv paketlar
        qs = self.queryset.filter(yil__gt=0, is_active=True) 
        
        if user.is_bolim():
            return qs.filter(user=user)
        if user.is_tarkibiy():
            return qs.filter(tarkibiy_tuzilma=user.tarkibiy_tuzilma)
        return qs



class PPRTasdiqlashFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name="status", lookup_expr="iexact")
    comment = django_filters.CharFilter(field_name="comment", lookup_expr="icontains")

    # Oy endi to‘g‘ridan-to‘g‘ri PPRYuborish dan olinadi
    oy = django_filters.NumberFilter(
        field_name="yuborish_paketi__oy"
    )

    yil = django_filters.NumberFilter(
        field_name="yuborish_paketi__yil"
    )

    class Meta:
        model = PPRTasdiqlash
        fields = ["status", "oy", "yil"]
        
        
    @property
    def qs(self):
        # super().qs => property, shuning uchun () ishlatilmaydi
        parent_qs = super().qs
        return parent_qs.filter(yuborish_paketi__is_active=True)











class PPRTasdiqlashViewSet(viewsets.ModelViewSet):
    queryset = PPRTasdiqlash.objects.all()
    serializer_class = PPRTasdiqlashSerializer
    # Bu ViewSet'ga faqat Rahbar va Adminlar kira oladi
    permission_classes = [permissions.IsAuthenticated] 
    pagination_class = CustomPagination

    
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PPRTasdiqlashFilter

    search_fields = [
        "comment",
        "user__username",
    ]

    ordering_fields = [
        "created_at",
        "status",
        "yuborish_paketi__oy",
        "yuborish_paketi__yil",
    ]
    ordering = ["-created_at"]


    def get_queryset(self):
        user = self.request.user

        # 🔹 GET (list, retrieve) → hamma auth bo‘lganlar ko‘rsin
        if self.action in ['list', 'retrieve']:
            return self.queryset.filter(yuborish_paketi__is_active=True)

        # 🔹 WRITE (create, update, delete) → faqat rahbar va admin
        if user.is_tarkibiy():
            return self.queryset.filter(
                yuborish_paketi__tarkibiy_tuzilma=user.tarkibiy_tuzilma
            )
        if user.is_superuser or user.is_admin():
            return self.queryset

        return self.queryset.none()

    def get_serializer_class(self):
        if self.action in ['list', 'retrieve']:
            return PPRTasdiqlashDetailSerializer
        return PPRTasdiqlashSerializer





class PPRJadvalViewSet(viewsets.ModelViewSet):
    serializer_class = PPRJadvalSerializer
    # ManyToMany bo'lgani uchun prefetch_related bazaga yukni kamaytiradi
    queryset = PPRJadval.objects.all().prefetch_related(
        'obyektlar', 
        'bajarildilar', 
        'bajarildilar__bajarilgan_obyektlar',
        'bajarildilar__images',
        'bajarildilar__user'
    ).order_by('-id')
    permission_classes = [permissions.IsAuthenticated, IsMonitoringReadOnly]
    pagination_class = CustomPagination
    
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = PPRJadvalFilter
    # Qidiruv fieldini yangiladik:
    search_fields = ['obyektlar__obyekt_nomi', 'ppr_turi__nomi', 'comment']
    ordering = ['-id']

    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset()

        if not user.is_authenticated:
            return qs.none()
        
        if 'pk' in self.kwargs or 'id' in self.kwargs:
            return qs
    
    
        # Query parametrlarni olish
        tuzilma_id = self.request.query_params.get("tuzilma")
        bolim_value = self.request.query_params.get("bolim_category")

        # 1. ADMIN VA MONITORING ROLI
        if user.is_superuser or user.is_admin() or user.is_monitoring():
            # Agar bo'lim filtri tanlanmagan bo'lsa, jadval bo'sh turadi
            if not bolim_value:
                return qs.none()
            
            # Bo'lim tanlanganda o'sha bo'limni (va agar tanlansa tuzilmani) ko'rsatadi
            qs = qs.filter(bolim_category__nomi__iexact=bolim_value)
            if tuzilma_id:
                qs = qs.filter(tarkibiy_tuzilma_id=tuzilma_id)
            return qs

        # 2. TARKIBIY (RAHBAR) ROLI
        if user.is_tarkibiy():
            # Rahbar ham bo'limni tanlamaguncha hech narsani ko'rmaydi
            if not bolim_value:
                return qs.none()
            
            # Faqat o'z tuzilmasi, tanlangan bo'lim va "jarayonda" bo'lmaganlar
            return qs.filter(
                tarkibiy_tuzilma=user.tarkibiy_tuzilma,
                bolim_category__nomi__iexact=bolim_value
            ).exclude(status="jarayonda")

        # 3. BO'LIM ROLI
        if user.is_bolim():
            user_bolim_cat = getattr(user.bolim_profile, 'bolim_category', None) if hasattr(user, 'bolim_profile') else None
            
            if not user_bolim_cat:
                return qs.none()

            # Bo'lim xodimi kirganda faqat o'z bo'limidagilarni ko'radi
            # Lekin tasdiqlanmagan bo'lsa, faqat o'zi yaratganini ko'radi
            return qs.filter(
                bolim_category=user_bolim_cat
            ).filter(
                Q(created_by=user) | Q(status__in=["tasdiqlandi", "bajarildi"])
            ).distinct()

        # 4. BEKAT ROLI
        if user.is_bekat() and user.bekat_nomi:
            return qs.filter(bekat=user.bekat_nomi, status__in=["tasdiqlandi", "bajarildi"])

        # Qolgan barcha holatlarda bo'sh qaytarish
        return qs.none()
    
    
    def perform_create(self, serializer):
        user = self.request.user
        serializer.save(
            created_by=user,
            tarkibiy_tuzilma=getattr(user, 'tarkibiy_tuzilma', None),
            bekat=getattr(user, 'bekat_nomi', None),
            bolim=getattr(user, 'bolim', None)
        )

    # def retrieve(self, request, *args, **kwargs):
    #     # 1. URL-dagi ID orqali asosiy jadval obyektini olamiz
    #     instance = self.get_object()
        
    #     # 2. Shu obyektning sanasi va ppr_turi bo'yicha bazadan qidiramiz
    #     # get_queryset() ni ishlatamizki, foydalanuvchining ko'rish huquqi (filtrlari) saqlanib qolsin
    #     queryset = self.get_queryset().filter(
    #         sana=instance.sana,
    #         ppr_turi=instance.ppr_turi
    #     )
        
    #     # 3. Natijani serializer orqali list ko'rinishida qaytaramiz
    #     serializer = self.get_serializer(queryset, many=True)
        
    #     return Response(serializer.data)
   
   
   
   
   
      
class PPRBajarildiViewSet(viewsets.ModelViewSet):
    serializer_class = PPRBajarildiSerializer
    permission_classes = [permissions.IsAuthenticated, IsMonitoringReadOnly]

    def get_queryset(self):
        user = self.request.user
        # select_related va prefetch_related foizni hisoblashda bazaga so'rovni kamaytiradi
        qs = PPRBajarildi.objects.select_related('jadval', 'user').prefetch_related(
            'bajarilgan_obyektlar', 'jadval__obyektlar'
        ).order_by('-created_at')

        if user.is_superuser or user.is_admin() or user.is_monitoring():
            return qs

        # Foydalanuvchi faqat o'ziga tegishli jadvallar hisobotini ko'radi
        return qs.filter(jadval__created_by=user)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get('pk') # Jadval ID
        try:
            jadval = PPRJadval.objects.prefetch_related('obyektlar').get(id=pk)
        except PPRJadval.DoesNotExist:
            return Response({"detail": "Jadval topilmadi"}, status=404)

        bajarildilar = self.get_queryset().filter(jadval_id=pk)
        
        # Umumiy foizni hisoblash mantiqi
        jami_count = jadval.obyektlar.count()
        bajarilgan_ids = bajarildilar.values_list('bajarilgan_obyektlar', flat=True).distinct()
        
        umumiy_foiz = 0
        if jami_count > 0:
            umumiy_foiz = round((len([x for x in bajarilgan_ids if x is not None]) / jami_count) * 100, 2)

        serializer = self.get_serializer(bajarildilar, many=True)

        return Response({
            "jadval_id": pk,
            "sana": jadval.sana,
            "jami_obyektlar_soni": jami_count,
            "joriy_status": jadval.status,
            "umumiy_bajarilish_foizi": umumiy_foiz,
            "tarix": serializer.data
        })
        
        
    def create(self, request, *args, **kwargs):
        
        
        serializer = self.get_serializer(data=request.data)
        
       
        serializer.is_valid(raise_exception=True) 
        
        self.perform_create(serializer)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    
    

    
    
    


class PPRYuborishStatusViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PPRJadval.objects.all()
    # 1. serializer_class qo'shildi (AssertionError ni oldini oladi)
    serializer_class = PPRYuborishStatusSerializer 
    pagination_class = CustomPagination
    permission_classes = [permissions.IsAuthenticated]
    
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'sana','bolim_category__nomi']
    search_fields = ["status"]
    ordering_fields = ['sana', 'id']
    ordering = ["-sana"]

    
    
    
    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset().filter(sana__isnull=False)
        bolim_value = self.request.query_params.get("bolim_category")

        # 1. ADMIN VA MONITORING
        if user.is_superuser or user.role in ['admin', 'monitoring']:
            if bolim_value:
                qs = qs.filter(bolim_category__nomi__iexact=bolim_value)
            return qs # Admin hamma narsani ko'rishi mumkin (yoki filtr bilan)

        # 2. TARKIBIY (RAHBAR) - O'z tuzilmasidagi barcha bo'limlarni ko'radi
        if user.role == 'tarkibiy':
            qs = qs.filter(tarkibiy_tuzilma=user.tarkibiy_tuzilma).exclude(status="jarayonda")
            if bolim_value:
                qs = qs.filter(bolim_category__nomi__iexact=bolim_value)
            return qs

        # 3. BO'LIM ROLI
        if user.role == 'bolim':
            user_bolim_cat = getattr(user.bolim_profile, 'bolim_category', None) if hasattr(user, 'bolim_profile') else None
            if not user_bolim_cat:
                return qs.none()
            return qs.filter(bolim_category=user_bolim_cat)

        return qs.none()

    def list(self, request, *args, **kwargs):
        # get_queryset orqali filtrlangan ma'lumotlarni olamiz
        qs = self.filter_queryset(self.get_queryset().annotate(
            v_yil=ExtractYear('sana'),
            v_oy=ExtractMonth('sana')
        ))

        group_dict = {}
        for item in qs:
            if item.v_yil is None or item.v_oy is None:
                continue
            
            # MUHIM: Guruhlash kalitiga bo'lim ID sini qo'shamiz
            # Shunda bitta oyda har xil bo'limlar alohida qator bo'ladi
            key = (item.v_yil, item.v_oy, item.bolim_category_id)
            if key not in group_dict:
                group_dict[key] = {
                    'yil': item.v_yil, 
                    'oy': item.v_oy, 
                    'ppr_list': [],
                    'bolim': item.bolim_category,
                    'tuzilma': item.tarkibiy_tuzilma
                }
            group_dict[key]['ppr_list'].append(item)

        result = []
        for g in group_dict.values():
            first_ppr = g['ppr_list'][0]
            curr_yil = g['yil']
            curr_oy = g['oy']

            yaratuvchi_user = first_ppr.created_by.username if first_ppr.created_by else "Noma'lum"

            # Tarix va qarorlar (Sizning kodingizdagidek)
            yil_search = [curr_yil, -abs(curr_yil)]
            yuborishlar = PPRYuborish.objects.filter(
                yil__in=yil_search, 
                oy=curr_oy,
                bolim_category=g['bolim'],
                tarkibiy_tuzilma=g['tuzilma']
            ).select_related("user").order_by('created_at')

            qarorlar = PPRTasdiqlash.objects.filter(
                yuborish_paketi__id__in=yuborishlar.values_list('id', flat=True)
            ).select_related("user").order_by('created_at')

            history_list = []
            # ... (history_list ga yuborishlar va qarorlarni append qilish logikasi o'zgarishsiz qoladi)
            for yub in yuborishlar:
                history_list.append({"id": yub.id, "type": "yuborish", "created_at": yub.created_at, "user": str(yub.user), "status": "yuborildi", "comment": yub.comment or "Yuborildi"})
            for qaror in qarorlar:
                history_list.append({"id": qaror.id, "type": "qaror", "created_at": qaror.created_at, "user": str(qaror.user), "status": qaror.status, "comment": qaror.comment or ""})
            history_list.sort(key=lambda x: x['created_at'])

            oxirgi_paket = yuborishlar.filter(yil__gt=0, is_active=True).order_by('-id').first()
            current_yuborish_id = oxirgi_paket.id if oxirgi_paket else None

            # Status aniqlash
            if any(p.status == 'tasdiqlandi' for p in yuborishlar):
                oy_status = 'tasdiqlandi'
            elif any(p.status == 'yuborildi' for p in yuborishlar):
                oy_status = 'yuborildi'
            elif any(p.status == 'rad_etildi' for p in yuborishlar):
                oy_status = 'rad_etildi'
            else:
                oy_status = 'jarayonda'

            if oy_status not in ['jarayonda', 'bajarildi']:
                result.append({
                    'id': first_ppr.id,
                    'yil': curr_yil,
                    'oy': curr_oy,
                    'oy_nomi': self.serializer_class.OY_NOMLARI.get(curr_oy),
                    'bolim_nomi': g['bolim'].nomi if g['bolim'] else "Noma'lum", # Frontend uchun qo'shimcha
                    'status': oy_status,
                    'yaratuvchi_user': yaratuvchi_user,
                    'yaratilgan_sana': first_ppr.sana.isoformat() if first_ppr.sana else None,
                    'tasdiqlashlar': history_list,
                    'yuborish_id': current_yuborish_id
                })

        result.sort(key=lambda x: x['id'], reverse=True)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(result, request)
        serializer = self.get_serializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)






class PPRJarayondaOylikViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = PPRJadval.objects.all()
    serializer_class = PPRJarayondaOylikSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPagination

    
    
    def get_queryset(self):
        user = self.request.user
        qs = super().get_queryset().filter(status='jarayonda', sana__isnull=False)
        bolim_value = self.request.query_params.get("bolim_category")

        # Admin / Monitoring / Tarkibiy (Hamma bo'limlarni ko'radi)
        if user.is_superuser or user.role in ['admin', 'monitoring', 'tarkibiy']:
            if user.role == 'tarkibiy':
                qs = qs.filter(tarkibiy_tuzilma=user.tarkibiy_tuzilma)
            
            if bolim_value:
                qs = qs.filter(bolim_category__nomi__iexact=bolim_value)
            return qs

        # Bo'lim (Faqat o'zinikini)
        if user.role == 'bolim':
            user_bolim_cat = getattr(user.bolim_profile, 'bolim_category', None) if hasattr(user, 'bolim_profile') else None
            return qs.filter(bolim_category=user_bolim_cat, created_by=user) if user_bolim_cat else qs.none()

        return qs.none()

    def list(self, request, *args, **kwargs):
        # O'zimizning get_queryset ni ishlatamiz
        qs = self.get_queryset().annotate(
            yil=ExtractYear('sana'),
            oy=ExtractMonth('sana')
        ).order_by('-sana')

        group_dict = {}
        for item in qs:
            # Tarkibiy uchun bo'limlar ajralib turishi uchun key'ga bolim_id qo'shildi
            key = (item.yil, item.oy, item.bolim_category_id)

            if key not in group_dict:
                group_dict[key] = {
                    "id": item.id,
                    "yil": item.yil,
                    "oy": item.oy,
                    "bolim_nomi": item.bolim_category.nomi if item.bolim_category else "Noma'lum",
                    "status": "jarayonda",
                    "yaratilgan_sana": item.sana
                }

        result = list(group_dict.values())
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(result, request)
        serializer = self.get_serializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)






    
    
    
class HujjatlarViewSet(viewsets.ModelViewSet):
    queryset = Hujjatlar.objects.all()
    serializer_class = HujjatlarSerializer
    pagination_class = CustomPagination



MONTHS_UZ = {
    1: "Yanvar",
    2: "Fevral",
    3: "Mart",
    4: "Aprel",
    5: "May",
    6: "Iyun",
    7: "Iyul",
    8: "Avgust",
    9: "Sentabr",
    10: "Oktabr",
    11: "Noyabr",
    12: "Dekabr",
}

   
class HujjatShabloniViewSet(viewsets.ModelViewSet):
    queryset = HujjatShabloni.objects.all().order_by('-created_at')
    serializer_class = HujjatShabloniSerializer
    
    permission_classes = [permissions.IsAuthenticated]

    filter_backends = [DjangoFilterBackend, SearchFilter]

    filterset_fields = ['tuzilma', 'nomi']

    search_fields = ['tuzilma__tuzilma_nomi', 'nomi', 'qoshimcha_nomi']

    def perform_create(self, serializer):
        serializer.save(yuklovchi=self.request.user) 
        
        



# ppr/views.py
class NotificationViewSet(viewsets.ModelViewSet):
    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()
    pagination_class = CustomPagination

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Notification.objects.none()

        ten_days_ago = timezone.now() - timedelta(days=10)

        # 1. BAZAVIY FILTRLAR (Eski va yangi mantiqni birlashtiramiz)
        
        # A) Tuzilmaga tegishli xabarlar (PPR, Ariza va Xarid uchun)
        user_tz = getattr(user, 'tarkibiy_tuzilma', None)
        
        # B) Bo'limga tegishli xabarlar (Faqat eski PPR/Ariza tizimi uchun)
        user_bolim_cat = None
        if hasattr(user, 'bolim_profile') and user.bolim_profile:
            user_bolim_cat = user.bolim_profile.bolim_category

        # Qidiruv shartlarini yig'amiz
        # Shart 1: Userning tuzilmasiga yuborilgan har qanday xabar
        query = Q(tarkibiy_tuzilma=user_tz) if user_tz else Q(pk__in=[])
        
        # Shart 2: Userning bo'limiga yuborilgan xabarlar (eskilar uchun)
        if user_bolim_cat:
            query |= Q(bolim_category=user_bolim_cat)
            
        # Shart 3: Monitoring uchun (Tuzilma va Bo'lim ko'rsatilmagan, lekin for_rahbar=True)
        if user.is_superuser or user.is_admin() or user.is_monitoring():
            # Monitoring xodimlari tuzilmasidan qat'i nazar hamma tasdiqlash xabarlarini ko'radi
            query |= Q(tarkibiy_tuzilma__isnull=True, bolim_category__isnull=True, for_rahbar=True)

        # Asosiy QuerySet
        base_qs = Notification.objects.filter(query).distinct()

        # 2. 10 KUNLIK MUDDAT FILTRI (Eski mantiq saqlangan holda)
        final_ids = []
        # optimization uchun prefetch ishlatamiz
        for obj in base_qs.prefetch_related('seen_by'):
            is_read = obj.seen_by.filter(id=user.id).exists()
            if is_read:
                # Agar o'qilgan bo'lsa, vaqtini tekshiramiz
                read_time_str = obj.read_times.get(str(user.id)) if obj.read_times else None
                if read_time_str:
                    try:
                        read_time = timezone.datetime.fromisoformat(read_time_str)
                        if read_time < ten_days_ago:
                            continue # 10 kundan o'tgan bo'lsa ro'yxatga qo'shmaymiz
                    except:
                        pass
            final_ids.append(obj.id)

        return Notification.objects.filter(id__in=final_ids).order_by('-created_at')

       

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Ko'rgan userlar ro'yxatiga qo'shish
        if request.user not in instance.seen_by.all():
            instance.seen_by.add(request.user)
            read_times = instance.read_times or {}
            read_times[str(request.user.id)] = timezone.now().isoformat()
            instance.read_times = read_times
            instance.save()
            
        return super().retrieve(request, *args, **kwargs)
    
    
    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        user = request.user
        
        is_read_sent = request.data.get("is_read")
        
        # 1. Bazaga yozish (PUT mantiqi)
        if is_read_sent is True:
            instance.seen_by.add(user)
            read_times = instance.read_times or {}
            read_times[str(user.id)] = timezone.now().isoformat()
            instance.read_times = read_times
            instance.save()
        elif is_read_sent is False:
            instance.seen_by.remove(user)
            read_times = instance.read_times or {}
            read_times.pop(str(user.id), None)
            instance.read_times = read_times
            instance.save()
        
        
        serializer = self.get_serializer(instance, context={'request': request})
        
        return Response(serializer.data, status=status.HTTP_200_OK)

    # Agar PATCH (partial update) ishlatmoqchi bo'lsangiz, uni ham update-ga yo'naltiring
    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)
    
    
    def list(self, request, *args, **kwargs):
        # 1. Asosiy querysetni olish
        queryset = self.filter_queryset(self.get_queryset())
        
        unread_count = queryset.exclude(seen_by=request.user).count()

        # 3. Pagination-ni amalga oshirish
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            # Standart pagination javobini olish
            paginated_response = self.get_paginated_response(serializer.data)
            
            # Javobga yangi maydonni qo'shish
            data = paginated_response.data
            data['unread_count'] = unread_count
            return Response(data)

        # Agar pagination ishlamasa (kam ehtimol)
        serializer = self.get_serializer(queryset, many=True)
        return Response({
            'results': serializer.data,
            'unread_count': unread_count
        })




     
class StatisticsChartAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        today = timezone.now().date()
        start_date = today - timedelta(days=90)

        type_ = request.GET.get("type")   # bekat / tuzilma
        obj_id = request.GET.get("id")

        ppr_filter = {}
        ariza_filter = {}

        bek_ct = ContentType.objects.get_for_model(Bekat)
        bolim_ct = ContentType.objects.get_for_model(Bolim)
        tuzilma_ct = ContentType.objects.get_for_model(TarkibiyTuzilma)

        # === KATTA ROLLAR ===
        if user.is_superuser or user.role in ["admin", "monitoring"]:
            if type_ and obj_id:
                if type_ == "bekat":
                    ppr_filter["obyekt_type"] = bek_ct
                    ppr_filter["obyekt_id"] = obj_id

                    ariza_filter["obyekt_type"] = bek_ct
                    ariza_filter["obyekt_id"] = obj_id

                elif type_ == "tuzilma":
                    ppr_filter["obyekt_type"] = tuzilma_ct
                    ppr_filter["obyekt_id"] = obj_id

                    ariza_filter["obyekt_type"] = tuzilma_ct
                    ariza_filter["obyekt_id"] = obj_id

        # === BEKAT ROLI ===
        elif user.role == "bekat" and user.bekat_nomi:
            ppr_filter["obyekt_type"] = bek_ct
            ppr_filter["obyekt_id"] = user.bekat_nomi.id

            ariza_filter["obyekt_type"] = bek_ct
            ariza_filter["obyekt_id"] = user.bekat_nomi.id

        # === BO‘LIM / TARKIBIY ===
        elif user.role in ["bolim", "tarkibiy"] and user.bolim:
            ppr_filter["obyekt_type"] = bolim_ct
            ppr_filter["obyekt_id"] = user.bolim.id

            ariza_filter["obyekt_type"] = bolim_ct
            ariza_filter["obyekt_id"] = user.bolim.id

        # === SANALAR ===
        all_dates = []
        d = start_date
        while d <= today:
            all_dates.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)

        # === PPR ===
        ppr_stats = (
            PPRJadval.objects
            .filter(
                sana__range=[start_date, today],
                **ppr_filter
            )
            .annotate(date=TruncDate("sana"))
            .values("date")
            .annotate(count=Count("id"))
        )

        # === ARIZA ===
        ariza_stats = (
            ArizaYuborish.objects
            .filter(
                status="bajarilgan",
                sana__range=[start_date, today],
                **ariza_filter
            )
            .annotate(date=TruncDate("sana"))
            .values("date")
            .annotate(count=Count("id"))
        )

        ppr_dict = {i["date"].strftime("%Y-%m-%d"): i["count"] for i in ppr_stats}
        ariza_dict = {i["date"].strftime("%Y-%m-%d"): i["count"] for i in ariza_stats}

        data = []
        for d in all_dates:
            data.append({
                "date": d,
                "mobile": ppr_dict.get(d, 0),
                "desktop": ariza_dict.get(d, 0),
            })

        return Response(data)





class DashboardBolimListView(APIView):
    """Filter dropdown uchun bo'limlar ro'yxati"""
    def get(self, request):
        user = request.user
        if user.role == 'tarkibiy':
            # Rahbar faqat o'z tuzilmasidagi bo'limlarni ko'radi
            bolimlar = BolimCategory.objects.filter(
                ppr_jadvallar__tarkibiy_tuzilma=user.tarkibiy_tuzilma
            ).distinct().values('id', 'nomi')
        else:
            # Adminlar barcha bo'limlarni ko'radi
            bolimlar = BolimCategory.objects.all().values('id', 'nomi')
            
        return Response(bolimlar)
    
    
@extend_schema(
    parameters=[
        OpenApiParameter(
            name="year",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Yil bo'yicha filter (masalan: 2026). Default: hozirgi yil"
        ),
        OpenApiParameter(
            name="bolim_category",  # Nomini o'zgartirdik
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Bo'lim nomi (BolimCategory nomi) bo'yicha filter"
        )
    ]
)
class PPRDashboardStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # 1. Filterni olish
        year_param = request.query_params.get("year")
        bolim_nomi = request.query_params.get("bolim_category") # Nom orqali olamiz
        bugun = timezone.now().date()
        limit_sana = bugun - timedelta(days=3)
        try:
            year = int(year_param) if year_param else timezone.now().year
        except ValueError:
            return Response({"error": "Year must be integer"}, status=400)

        # 2. Asosiy Queryset (Yil bo'yicha)
        queryset = PPRJadval.objects.filter(sana__year=year)

        # 3. Bo'lim nomi bo'yicha filterlash (iexact - katta/kichik harfni farqlamaydi)
        if bolim_nomi:
            queryset = queryset.filter(bolim_category__nomi__iexact=bolim_nomi)

        months_map = {
            1: "Yanvar", 2: "Fevral", 3: "Mart", 4: "Aprel",
            5: "May", 6: "Iyun", 7: "Iyul", 8: "Avgust",
            9: "Sentabr", 10: "Oktabr", 11: "Noyabr", 12: "Dekabr"
        }

        # 4. Oy + Bo'lim bo'yicha agregatsiya
        stats = queryset.values(
            'sana__month',
            'bolim_category__id',
            'bolim_category__nomi'
        ).annotate(
            muddati_otgan=Count('id', filter=Q(status='tasdiqlandi', sana__lt=limit_sana)),
            bajarilgan=Count('id', filter=Q(status='bajarildi')),
            umumiy=Count('id')
        ).order_by('sana__month')

        result = []

        # 5. Ma'lumotlarni oylar bo'yicha yig'ish
        for m_id, m_name in months_map.items():
            bolimlar_stats = [
                {
                    "bolim_id": item['bolim_category__id'],
                    "bolim_nomi": item['bolim_category__nomi'],
                    "muddati_otgan": item['muddati_otgan'],
                    "bajarilgan": item['bajarilgan'],
                    "umumiy": item['umumiy']
                }
                for item in stats if item['sana__month'] == m_id
            ]

            result.append({
                "oy_id": m_id,
                "oy_nomi": m_name,
                "tuzilmalar": bolimlar_stats
            })

        # 6. Yillik umumiy
        yearly = queryset.aggregate(
            muddati_otgan=Count('id', filter=Q(muddat=True)),
            bajarilgan=Count('id', filter=Q(status='bajarildi')),
            umumiy=Count('id')
        )

        return Response({
            "year": year,
            "filter_bolim_category": bolim_nomi, # Nomni qaytaramiz
            "months": result,
            "yearly_summary": yearly
        })
  
  
  


class DashboardStatsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        now = timezone.now()
        this_year = now.year
        last_year = this_year - 1
        this_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 1. Huquqni tekshirish
        is_global_viewer = user.role in ["admin", "monitoring"] or user.is_superuser
        
        # 2. Filtrlarni shakllantirish
        if not is_global_viewer:
            if not user.tarkibiy_tuzilma:
                return Response({"error": "Sizga tarkibiy tuzilma biriktirilmagan"}, status=403)
            
            tuzilma_filter = Q(tarkibiy_tuzilma=user.tarkibiy_tuzilma)
            ariza_tuzilma_filter = Q(tuzilmalar=user.tarkibiy_tuzilma)
            user_filter = Q(tarkibiy_tuzilma=user.tarkibiy_tuzilma)
            # Yillik jadvalda tuzilma filteri (agar unda ham bo'lsa)
            yillik_filter = Q(tarkibiy_tuzilma=user.tarkibiy_tuzilma)
        else:
            selected_id = request.query_params.get("tarkibiy_tuzilma")
            if selected_id:
                tuzilma_filter = Q(tarkibiy_tuzilma_id=selected_id)
                ariza_tuzilma_filter = Q(tuzilmalar__id=selected_id)
                user_filter = Q(tarkibiy_tuzilma_id=selected_id)
                yillik_filter = Q(tarkibiy_tuzilma_id=selected_id)
            else:
                tuzilma_filter = Q()
                ariza_tuzilma_filter = Q()
                user_filter = Q()
                yillik_filter = Q()

        def calculate_growth(current, previous):
            if previous == 0:
                return 100.0 if current > 0 else 0.0
            return round(((current - previous) / previous) * 100, 2)

        # --- 1. YILLIK PPRLAR (Jadval + Yillik) ---
        ppr_this = (
            PPRJadval.objects.filter(tuzilma_filter, sana__year=this_year).count()
        )
        ppr_last = (
            PPRJadval.objects.filter(tuzilma_filter, sana__year=last_year).count() 
        )

        # --- 2. MAVJUD ARIZALAR ---
        ariza_this = ArizaYuborish.objects.filter(ariza_tuzilma_filter, sana__year=this_year).distinct().count()
        ariza_last = ArizaYuborish.objects.filter(ariza_tuzilma_filter, sana__year=last_year).distinct().count()

        # --- 3. BAJARILGAN ARIZALAR ---
        completed_this = ArizaYuborish.objects.filter(ariza_tuzilma_filter, sana__year=this_year, status="bajarilgan").distinct().count()
        completed_last = ArizaYuborish.objects.filter(ariza_tuzilma_filter, sana__year=last_year, status="bajarilgan").distinct().count()

        # --- 4. FOYDALANUVCHILAR ---
        total_users = CustomUser.objects.filter(user_filter).count()
        users_until_this_month = CustomUser.objects.filter(user_filter, date_joined__lt=this_month_start).count()

        # Natijani qaytarish
        return Response({
            "stats": {
                "ppr": {
                    "title": "Yillik PPRlar",
                    "count": ppr_this,
                    "growth_percentage": calculate_growth(ppr_this, ppr_last)
                },
                "total_arizalar": {
                    "title": "Mavjud Arizalar",
                    "count": ariza_this,
                    "growth_percentage": calculate_growth(ariza_this, ariza_last)
                },
                "completed_arizalar": {
                    "title": "Bajarilgan arizalar",
                    "count": completed_this,
                    "growth_percentage": calculate_growth(completed_this, completed_last)
                },
                "users": {
                    "title": "Foydalanuvchilar",
                    "count": total_users,
                    "growth_percentage": calculate_growth(total_users, users_until_this_month)
                }
            },
            "view_info": {
                "tuzilma": user.tarkibiy_tuzilma.tuzilma_nomi if not is_global_viewer else "Barchasi",
                "mode": "Global" if is_global_viewer else "Local"
            }
        })
  
  
  
  
  
  
  
class TopTuzilmalarDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Tarkibiy tuzilmalarni va ulardagi arizalar sonini hisoblash
        top_tuzilmalar = TarkibiyTuzilma.objects.annotate(
            bajarilgan_soni=Count(
                'arizalar', # ArizaYuborish modelidagi related_name='arizalar' bo'lsa
                filter=Q(arizalar__status='bajarilgan')
            ),
            umumiy_kelgan_soni=Count('arizalar')
        ).order_by('-bajarilgan_soni')[:10]

        data = []
        for t in top_tuzilmalar:
            # Bevosita TarkibiyTuzilma modelidagi 'rahbari' maydonini olamiz
            data.append({
                "tuzilma_nomi": t.tuzilma_nomi,
                "rahbari": t.rahbari if t.rahbari else "Noma'lum", # Modelingizdagi maydon
                "bajarilgan_soni": t.bajarilgan_soni,
                "umumiy_kelgan_soni": t.umumiy_kelgan_soni,
            })

        serializer = TuzilmaDashboardSerializer(data, many=True)
        return Response(serializer.data)
    



class PPRDashboardStatsNEW(APIView):

    def get(self, request):

        month = request.query_params.get("month")
        year = request.query_params.get("year")

        # PPR filter
        ppr_filter = Q()

        if month:
            ppr_filter &= Q(pprjadval__sana__month=month)

        if year:
            ppr_filter &= Q(pprjadval__sana__year=year)

        # Hamma tuzilmalarni olib LEFT JOIN qilish
        stats = (
            TarkibiyTuzilma.objects
            .annotate(
                umumiy_ppr=Count(
                    "pprjadval",
                    filter=ppr_filter,
                    distinct=True
                ),
                bajarilgan_ppr=Count(
                    "pprjadval",
                    filter=ppr_filter & Q(pprjadval__status="bajarildi"),
                    distinct=True
                )
            )
            .values(
                "id",
                "tuzilma_nomi",
                "umumiy_ppr",
                "bajarilgan_ppr"
            )
            .order_by("id")
        )

        data = []

        for item in stats:

            jami = item["umumiy_ppr"]
            bajarilgan = item["bajarilgan_ppr"]

            foiz = 0
            if jami > 0:
                foiz = round((bajarilgan / jami) * 100, 2)

            data.append({
                "tuzilma_id": item["id"],
                "tuzilma_nomi": item["tuzilma_nomi"],
                "umumiy_ppr": jami,
                "bajarilgan_ppr": bajarilgan,
                "bajarilish_foizi": foiz
            })

        return Response({"data": data})



    
class XaridArizaFilter(django_filters.FilterSet):
    tuzilma = django_filters.NumberFilter(field_name='tuzilmalar__id')
    tuzilma_nomi = django_filters.CharFilter(field_name='tuzilmalar__tuzilma_nomi', lookup_expr='icontains')
    status = django_filters.CharFilter(lookup_expr='exact')
    sana_dan = django_filters.DateFilter(field_name='sana', lookup_expr='gte')
    
    class Meta:
        model = XaridAriza
        fields = ['status', 'tuzilma', 'created_by']    
    
    
    
    
class XaridArizaViewSet(viewsets.ModelViewSet):
    pagination_class = CustomPagination
    serializer_class = XaridArizaSerializer
    permission_classes = [IsAuthenticated]
    
    # Filtr backendlarini qo'shamiz
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = XaridArizaFilter
    
    # Qidiruv maydonlari (Search)
    search_fields = ['comment', 'tuzilmalar__tuzilma_nomi', 'created_by__username']
    # Saralash maydonlari (Ordering)
    ordering_fields = ['id', 'sana', 'status']
    
    def get_queryset(self):
        user = self.request.user
        queryset = XaridAriza.objects.all().prefetch_related('steplar', 'tuzilmalar')

        if user.is_superuser or user.is_admin() or user.is_monitoring():
            return queryset.order_by('-id')

        return queryset.filter(created_by=user).order_by('-id')

    def perform_create(self, serializer):
            user = self.request.user
            
            # 1. Monitoring huquqini tekshirish
            if user.is_monitoring() and not user.is_superuser:
                raise serializers.ValidationError("Monitoring xodimi yangi ariza yarata olmaydi.")
            
            # 2. Faqat bitta save() chaqiriladi va barcha kerakli maydonlar birga yuboriladi
            serializer.save(
                created_by=user,
                kim_tomonidan=user
            )

    def update(self, request, *args, **kwargs):
        user = request.user
        instance = self.get_object()

        # 1. Ruxsatni tekshirish
        if not (user.is_superuser or user.is_admin() or user.is_monitoring()):
            return Response({"error": "Sizda statusni o'zgartirish huquqi yo'q."}, status=403)

        
        data = request.data.copy()
        if 'tuzilmalar' in data:
            data.pop('tuzilmalar') 

        new_status = data.get("status")
        
        # 3. Mantiqiy tekshiruv
        if new_status == 'tasdiqlandi' and instance.status != 'kelishildi':
            return Response({
                "error": "Hali barcha tuzilmalar kelishmagan. Tasdiqlash mumkin emas."
            }, status=400)

        # 4. Saqlash (partial=True tufayli faqat kelgan maydonlar o'zgaradi)
        serializer = self.get_serializer(instance, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            "message": f"Ariza #{instance.id} statusi '{new_status}' holatiga o'tkazildi.",
            "data": serializer.data
        })



class XaridArizaFilterKelgan(django_filters.FilterSet):
    kim_tomonidan_nomi = django_filters.CharFilter(
        field_name='kim_tomonidan__tarkibiy_tuzilma__tuzilma_nomi', 
        lookup_expr='icontains'
    )

    
    status = django_filters.CharFilter(field_name='status', lookup_expr='exact')

    
    sana_dan = django_filters.DateFilter(field_name='sana', lookup_expr='gte')
    sana_gacha = django_filters.DateFilter(field_name='sana', lookup_expr='lte')

    class Meta:
        model = XaridAriza
        fields = ['status', 'kim_tomonidan', 'created_by']

    def filter_by_any_structure(self, queryset, name, value):
        from django.db.models import Q
        return queryset.filter(
            Q(kim_tomonidan__tarkibiy_tuzilma__tuzilma_nomi__icontains=value) |
            Q(kim_tomonidan__bolim__icontains=value) |
            Q(kim_tomonidan__bekat_nomi__icontains=value)
        ).distinct()



# 2. Tuzilmalarga "Kelgan arizalar" uchun
class XaridKelganlarViewSet(mixins.ListModelMixin, 
                            mixins.RetrieveModelMixin, 
                            viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = CustomPagination
    search_fields = ['comment', 'tuzilmalar__tuzilma_nomi', 'created_by__username']
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = XaridArizaFilterKelgan
    ordering_fields = ['id', 'sana', 'status']

    def get_queryset(self):
        user = self.request.user
        queryset = XaridAriza.objects.all().prefetch_related('steplar', 'tuzilmalar').distinct()
        if user.is_superuser or user.is_admin() or user.is_monitoring():
            return queryset.order_by('-id')
        
        user_tz = getattr(user, 'tarkibiy_tuzilma', None) or \
                  getattr(user, 'bekat_nomi', None) or \
                  getattr(user, 'bolim', None)
        return XaridAriza.objects.filter(tuzilmalar=user_tz).distinct().order_by('-id')

    def get_serializer_class(self):
        # Agar qaror qabul qilish amali bo'lsa, status va comment formasini chiqar
        if self.action == 'qaror_qabul_qilish':
            return XaridQarorActionSerializer
        return XaridArizaSerializer

    @action(detail=True, methods=['post'])
    def qaror_qabul_qilish(self, request, pk=None):
        xarid = self.get_object()
        user = request.user
        user_tz = getattr(user, 'tarkibiy_tuzilma', None) or \
                  getattr(user, 'bekat_nomi', None) or \
                  getattr(user, 'bolim', None)

        # 1. Serializer orqali ma'lumotlarni validatsiya qilish
        serializer = XaridQarorActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        new_status = serializer.validated_data.get('status')
        comment = serializer.validated_data.get('comment', '')

        # 2. Tekshiruv: Avval qaror berilganmi?
        if XaridStep.objects.filter(xarid=xarid, tuzilma=user_tz).exists():
            return Response({"error": "Siz ushbu arizaga munosabat bildirib bo'lgansiz."}, 
                            status=status.HTTP_400_BAD_REQUEST)

        # 3. Step yaratish
        XaridStep.objects.create(
            xarid=xarid,
            tuzilma=user_tz,
            user=user,
            status=new_status,
            comment=comment
        )

        # 4. Asosiy Ariza statusini yangilash
        if new_status == 'rad_etildi':
            
            xarid.status = 'rad_etildi'
        else:
            
            total_required = xarid.tuzilmalar.count()
            
            current_agreed = xarid.steplar.filter(status='kelishildi').count()
            
            
            if current_agreed >= total_required:
                xarid.status = 'kelishildi'
            
        
        xarid.save()
        return Response({
            "message": f"Qaroringiz qabul qilindi. Ariza statusi: {xarid.status}",
            "status": xarid.status
        }, status=status.HTTP_201_CREATED)
    
    
    
    