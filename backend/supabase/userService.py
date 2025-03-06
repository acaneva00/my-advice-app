import uuid
from .supabase import supabase

class UserService:
    """Service for handling user operations with Supabase"""
    
    async def createUser(self, userData):
        """Create a new user account"""
        try:
            # Prepare the data
            data = {
                "user_uuid": userData.get("id", str(uuid.uuid4())),
                "user_email": userData["email"],
                "first_name": userData.get("firstName", "Anonymous"),
                "last_name": userData.get("lastName", "User"),
                "phone": userData.get("phone"),
                "privacy_version": userData.get("privacyVersion", "1.0"),
                "terms_version": userData.get("termsVersion", "1.0"),
                "current_age": userData.get("currentAge"),
                "current_balance": userData.get("currentBalance"),
                "current_income": userData.get("currentIncome"),
                "retirement_age": userData.get("retirementAge"),
                "current_fund": userData.get("currentFund")
            }
            
            # Call the Supabase function
            result = await supabase.query(
                "/rest/v1/rpc/create_user_with_profile",
                method="POST",
                data=data
            )
            
            return {"userId": result}
        except Exception as e:
            print(f"Error creating user: {e}")
            return {"userId": data["user_uuid"], "error": str(e)}
    
    async def getUserProfile(self, userId):
        """Get user profile data"""
        try:
            result = await supabase.query(
                f"/rest/v1/user_profile_summary?user_id=eq.{userId}",
                method="GET"
            )
            
            if result and len(result) > 0:
                return result[0]
            return {}
        except Exception as e:
            print(f"Error fetching user profile: {e}")
            return {}
    
    async def updateFinancialProfile(self, userId, profileData):
        """Update user financial profile"""
        try:
            data = {
                "p_user_id": userId,
                "p_current_age": profileData.get("currentAge"),
                "p_current_balance": profileData.get("currentBalance"),
                "p_current_income": profileData.get("currentIncome"),
                "p_retirement_age": profileData.get("retirementAge"),
                "p_current_fund": profileData.get("currentFund"),
                "p_super_included": profileData.get("superIncluded"),
                "p_retirement_income_option": profileData.get("retirementIncomeOption"),
                "p_retirement_income": profileData.get("retirementIncome")
            }
            
            # Call the Supabase function
            result = await supabase.query(
                "/rest/v1/rpc/update_financial_profile",
                method="POST",
                data=data
            )
            
            return {"profileId": result}
        except Exception as e:
            print(f"Error updating financial profile: {e}")
            return {"profileId": str(uuid.uuid4()), "error": str(e)}