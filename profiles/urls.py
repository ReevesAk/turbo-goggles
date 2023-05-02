from django.urls import path
 
from .views import BusinessView, UserView, MemberView

urlpatterns = [
    path('busniess/<int:id>/', MemberView.as_view(), name='business'),
    path('user/<int:id>/', MemberView.as_view(), name='user'),
    path('member/<int:id>/', MemberView.as_view(), name='member')
]