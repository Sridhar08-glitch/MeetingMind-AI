"""AI meeting chat API — conversations, messages, ask, citations."""
from __future__ import annotations

from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request

from apps.common.responses import error_response, success_response
from apps.meetings.models import ChatConversation, ChatMessage, Meeting, MessageCitation
from apps.meetings.services.chat import SUGGESTED_QUESTIONS, ChatService, start_conversation


# --- serializers ------------------------------------------------------------
class MessageCitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = MessageCitation
        fields = ("id", "index", "start_time", "end_time", "snippet", "segment")
        read_only_fields = fields


class ChatMessageSerializer(serializers.ModelSerializer):
    citations = MessageCitationSerializer(source="message_citations", many=True, read_only=True)

    class Meta:
        model = ChatMessage
        fields = (
            "id", "role", "content", "found", "provider", "model_used",
            "prompt_version", "inference_ms", "citations", "created_at",
        )
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(source="messages.count", read_only=True)

    class Meta:
        model = ChatConversation
        fields = ("id", "meeting", "title", "message_count", "created_at", "updated_at")
        read_only_fields = ("id", "message_count", "created_at", "updated_at")


class ConversationDetailSerializer(ConversationSerializer):
    messages = ChatMessageSerializer(many=True, read_only=True)

    class Meta(ConversationSerializer.Meta):
        fields = ConversationSerializer.Meta.fields + ("messages",)


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=2000)


# --- permission -------------------------------------------------------------
class OwnsMeeting(BasePermission):
    message = "You do not have permission to access this conversation."

    def has_object_permission(self, request, view, obj) -> bool:
        return obj.meeting.owner_id == request.user.id


# --- viewset ----------------------------------------------------------------
class ConversationViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """Owner-scoped chat conversations. One meeting → many conversations."""

    permission_classes = [IsAuthenticated, OwnsMeeting]
    search_fields = ("title",)
    filterset_fields = ("meeting",)
    ordering = ("-created_at",)

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return ChatConversation.objects.none()
        qs = ChatConversation.objects.filter(meeting__owner=self.request.user).select_related("meeting")
        if self.action == "retrieve":
            return qs.prefetch_related("messages__message_citations")
        return qs

    def get_serializer_class(self):
        return ConversationDetailSerializer if self.action == "retrieve" else ConversationSerializer

    def create(self, request: Request, *args, **kwargs):
        meeting_id = request.data.get("meeting")
        meeting = Meeting.objects.filter(id=meeting_id, owner=request.user).first()
        if meeting is None:
            return error_response("Meeting not found.", code="not_found", status=404)
        conv = start_conversation(meeting, title=request.data.get("title", "New conversation"),
                                  actor=request.user)
        return success_response(data=ConversationSerializer(conv).data, message="Conversation started.", status=201)

    def perform_update(self, serializer):
        serializer.instance.set_acting_user(self.request.user)
        serializer.save()

    def perform_destroy(self, instance):
        instance.set_acting_user(self.request.user)
        instance.delete()

    def destroy(self, request, *args, **kwargs):
        self.perform_destroy(self.get_object())
        return success_response(message="Conversation deleted.")

    @action(detail=True, methods=["post"])
    def ask(self, request: Request, pk=None):
        conversation = self.get_object()
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assistant = ChatService().ask(
            conversation, serializer.validated_data["question"], actor=request.user
        )
        return success_response(data=ChatMessageSerializer(assistant).data)

    @action(detail=True, methods=["get"])
    def messages(self, request: Request, pk=None):
        conversation = self.get_object()
        data = ChatMessageSerializer(
            conversation.messages.prefetch_related("message_citations"), many=True
        ).data
        return success_response(data=data)


class SuggestedQuestionsView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request: Request):
        return success_response(data=SUGGESTED_QUESTIONS)
