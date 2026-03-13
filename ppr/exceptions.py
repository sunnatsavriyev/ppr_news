from rest_framework.views import exception_handler
from rest_framework.exceptions import ValidationError

def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        custom_errors = {}
        
        if isinstance(exc, ValidationError):
            for field, errors in response.data.items():
                if isinstance(errors, list):
                    translated_errors = []
                    for error in errors:
                        err_str = str(error)
                        
                        # 1. Bo'sh maydonlar uchun
                        if "This field may not be blank" in err_str or "This field may not be null" in err_str:
                            translated_errors.append("Ushbu maydon bo‘sh bo‘lishi mumkin emas")
                        
                        # 2. To'ldirilishi shart bo'lgan maydonlar
                        elif "This field is required" in err_str:
                            translated_errors.append("Ushbu maydon to‘ldirilishi shart")
                        
                        # 3. Parol va belgilar soni cheklovi (Siz so'ragan xato)
                        elif "Ensure this field has at least" in err_str:
                            # Masalan: "Ensure this field has at least 6 characters."
                            count = "".join(filter(str.isdigit, err_str)) # Sonni ajratib olamiz
                            translated_errors.append(f"Ushbu maydon kamida {count} ta belgidan iborat bo‘lishi kerak")
                        
                        # 4. Maksimal belgilar soni
                        elif "Ensure this field has no more than" in err_str:
                            count = "".join(filter(str.isdigit, err_str))
                            translated_errors.append(f"Ushbu maydonda belgilar soni {count} tadan oshmasligi kerak")
                        
                        # 5. Unikallik (Username band bo'lsa)
                        elif "A user with that username already exists" in err_str:
                            translated_errors.append("Bunday foydalanuvchi nomi band, boshqasini tanlang")

                        # 6. Boshqa xatolar bo'lsa o'zini qoldiramiz
                        else:
                            translated_errors.append(err_str)
                    
                    custom_errors[field] = translated_errors
                else:
                    custom_errors[field] = errors
            
            # Umumiy message har doim bo'lishi uchun
            custom_errors["message"] = "Ma'lumotlarni yuborishda xatolik yuz berdi!"
            response.data = custom_errors

    return response